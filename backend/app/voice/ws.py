"""Voice WebSocket. JSON frames in both directions.

client -> server: transcript.partial | transcript.final | audio.chunk | audio.end | interrupt | ping
server -> client: ready | transcript.final (from server ASR) | assistant.thinking | assistant.text |
                  tts.audio | tts.cancel | idle_prompt | closing | error | pong
Text and voice share run_turn(), so the conversation state is identical across modalities.
"""
import asyncio
import base64
import logging
import threading

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.agent.runner import ConversationNotFound, TurnCancelled, run_turn
from app.core.config import get_settings
from app.core.security import decode_token
from app.db.models import Customer
from app.db.session import SessionLocal
from app.voice import asr, tts

log = logging.getLogger("voice")
router = APIRouter()


def _turn_sync(customer_id: int, conv_id: int | None, text: str, cancel: threading.Event) -> dict:
    with SessionLocal() as db:  # own session per turn: sessions are not thread-safe
        customer = db.get(Customer, customer_id)
        return run_turn(db, customer, text, conv_id, "voice", None, cancel)


@router.websocket("/ws/voice")
async def voice(ws: WebSocket, token: str, conversation_id: int | None = None):
    cid = decode_token(token)
    if cid is None:
        await ws.close(code=4401)
        return
    await ws.accept()
    s = get_settings()
    conv_id = conversation_id
    task: asyncio.Task | None = None
    cancel: threading.Event | None = None
    audio_buf, audio_mime, warned = bytearray(), "audio/webm", False

    async def interrupt(notify: bool = True):
        nonlocal task, cancel
        if task and not task.done():
            cancel.set()
            task.cancel()
            if notify:
                await ws.send_json({"type": "tts.cancel"})
        task = None

    async def handle_turn(text: str, evt: threading.Event):
        nonlocal conv_id
        await ws.send_json({"type": "assistant.thinking"})
        try:
            res = await asyncio.to_thread(_turn_sync, cid, conv_id, text, evt)
            conv_id = res["conversation_id"]
            await ws.send_json({"type": "assistant.text", **res})
            if s.server_tts:
                try:
                    audio, mime = await asyncio.to_thread(tts.synthesize, res["reply"])
                    await ws.send_json({"type": "tts.audio", "mime": mime, "data": base64.b64encode(audio).decode()})
                except Exception:
                    log.warning("server tts failed; client falls back to browser speech")
        except (TurnCancelled, asyncio.CancelledError):
            evt.set()
        except ConversationNotFound:
            await ws.send_json({"type": "error", "code": "conversation_not_found"})
        except Exception:
            log.exception("voice turn failed")
            await ws.send_json({"type": "error", "code": "turn_failed",
                                "message": "Something went wrong. Nothing was changed; please try again."})

    async def start_turn(text: str):
        nonlocal task, cancel
        await interrupt(notify=False)
        cancel = threading.Event()
        task = asyncio.create_task(handle_turn(text, cancel))

    await ws.send_json({"type": "ready", "conversation_id": conv_id})
    try:
        while True:
            try:
                msg = await asyncio.wait_for(ws.receive_json(), timeout=s.voice_idle_seconds)
            except asyncio.TimeoutError:
                if task and not task.done():
                    continue  # still working, not silence
                if not warned:
                    warned = True
                    await ws.send_json({"type": "idle_prompt", "text": "Are you still there?"})
                    continue
                await ws.send_json({"type": "closing", "reason": "silence"})
                await ws.close()
                return
            warned = False
            kind = msg.get("type")
            if kind == "ping":
                await ws.send_json({"type": "pong"})
            elif kind == "interrupt":
                await interrupt()
            elif kind == "transcript.partial":
                if (msg.get("text") or "").strip():
                    await interrupt()  # user is speaking: barge-in cancels in-flight work and playback
            elif kind == "transcript.final":
                text = (msg.get("text") or "").strip()[:1000]
                if text:
                    await start_turn(text)
            elif kind == "audio.chunk":
                audio_mime = msg.get("mime") or audio_mime
                if len(audio_buf) < 5_000_000:
                    audio_buf.extend(base64.b64decode(msg.get("data", "")))
            elif kind == "audio.end":
                data, audio_buf = bytes(audio_buf), bytearray()
                try:
                    text = await asyncio.to_thread(asr.transcribe, data, audio_mime) if data else ""
                except Exception:
                    log.exception("asr failed")
                    await ws.send_json({"type": "error", "code": "asr_failed",
                                        "message": "I couldn't process the audio. Please type instead or try again."})
                    continue
                if text:
                    await ws.send_json({"type": "transcript.final", "text": text})
                    await start_turn(text)
    except WebSocketDisconnect:
        pass
    finally:
        await interrupt(notify=False)
