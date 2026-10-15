import json
import time

import pytest
from starlette.websockets import WebSocketDisconnect

from app.agent.runner import TurnCancelled
from app.core.config import get_settings


@pytest.fixture
def token(client):
    return client.post("/auth/register", json={"email": "v@example.com", "name": "V",
                                               "password": "password123"}).json()["token"]


@pytest.fixture(autouse=True)
def fake_classifier(monkeypatch):
    monkeypatch.setattr("app.agent.nodes.classify_llm", lambda *a, **k: {
        "intent": "other", "standalone_question": None, "slots": {}})


def test_rejects_bad_token(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/voice?token=bad") as ws:
            ws.receive_json()


def test_voice_turn_shares_state_with_text(client, token):
    with client.websocket_connect(f"/ws/voice?token={token}") as ws:
        assert ws.receive_json()["type"] == "ready"
        ws.send_json({"type": "transcript.partial", "text": "hel"})   # partials never start a turn
        ws.send_json({"type": "transcript.final", "text": "hello there"})
        assert ws.receive_json()["type"] == "assistant.thinking"
        out = ws.receive_json()
        assert out["type"] == "assistant.text" and out["conversation_id"]
        cid = out["conversation_id"]
    # same conversation is visible over HTTP, with the voice-modality messages
    msgs = client.get(f"/conversations/{cid}/messages", headers={"Authorization": f"Bearer {token}"}).json()
    assert [m["modality"] for m in msgs] == ["voice", "voice"]
    r = client.post("/chat/message", json={"text": "hi again", "conversation_id": cid},
                    headers={"Authorization": f"Bearer {token}"})
    assert r.json()["conversation_id"] == cid


def test_barge_in_cancels_inflight_turn_and_recovers(client, token, monkeypatch):
    def slow(customer_id, conv_id, text, cancel):
        if text == "slow":
            cancel.wait(3)
            raise TurnCancelled()
        return {"conversation_id": 1, "reply": "fast reply", "citations": [], "intent": "other"}
    monkeypatch.setattr("app.voice.ws._turn_sync", slow)
    with client.websocket_connect(f"/ws/voice?token={token}") as ws:
        ws.receive_json()
        ws.send_json({"type": "transcript.final", "text": "slow"})
        assert ws.receive_json()["type"] == "assistant.thinking"
        ws.send_json({"type": "interrupt"})
        assert ws.receive_json()["type"] == "tts.cancel"
        ws.send_json({"type": "transcript.final", "text": "fast"})
        assert ws.receive_json()["type"] == "assistant.thinking"
        out = ws.receive_json()
        assert out["type"] == "assistant.text" and out["reply"] == "fast reply"   # nothing from the cancelled turn


def test_new_utterance_supersedes_running_turn(client, token, monkeypatch):
    def slow(customer_id, conv_id, text, cancel):
        if text == "first":
            cancel.wait(3)
            raise TurnCancelled()
        return {"conversation_id": 1, "reply": f"re:{text}", "citations": [], "intent": "other"}
    monkeypatch.setattr("app.voice.ws._turn_sync", slow)
    with client.websocket_connect(f"/ws/voice?token={token}") as ws:
        ws.receive_json()
        ws.send_json({"type": "transcript.final", "text": "first"})
        ws.receive_json()
        ws.send_json({"type": "transcript.final", "text": "second"})
        frames = [ws.receive_json() for _ in range(2)]
        assert [f["type"] for f in frames] == ["assistant.thinking", "assistant.text"]
        assert frames[1]["reply"] == "re:second"


def test_silence_prompts_then_closes(client, token, monkeypatch):
    monkeypatch.setattr(get_settings(), "voice_idle_seconds", 0.3)
    with client.websocket_connect(f"/ws/voice?token={token}") as ws:
        ws.receive_json()
        assert ws.receive_json()["type"] == "idle_prompt"
        assert ws.receive_json() == {"type": "closing", "reason": "silence"}


def test_asr_failure_is_reported_not_fatal(client, token, monkeypatch):
    import base64

    def boom(*a, **k):
        raise RuntimeError("asr down")
    monkeypatch.setattr("app.voice.ws.asr.transcribe", boom)
    with client.websocket_connect(f"/ws/voice?token={token}") as ws:
        ws.receive_json()
        ws.send_json({"type": "audio.chunk", "mime": "audio/webm", "data": base64.b64encode(b"abc").decode()})
        ws.send_json({"type": "audio.end"})
        assert ws.receive_json()["code"] == "asr_failed"
        ws.send_json({"type": "ping"})
        assert ws.receive_json()["type"] == "pong"                   # connection still usable
