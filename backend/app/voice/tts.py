"""Optional server-side TTS (Gemini). Off by default (SERVER_TTS=false): the browser speaks replies instead."""
import io
import wave
from google.genai import types
from app.agent.llm import _get_client
from app.core.config import get_settings


def synthesize(text: str) -> tuple[bytes, str]:
    res = _get_client().models.generate_content(
        model=get_settings().tts_model, contents=text[:800],
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Kore")))))
    pcm = res.candidates[0].content.parts[0].inline_data.data  # 24 kHz, 16-bit mono PCM
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(pcm)
    return buf.getvalue(), "audio/wav"
