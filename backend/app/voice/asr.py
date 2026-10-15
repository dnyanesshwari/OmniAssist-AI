"""Server-side ASR fallback (Gemini). Primary path in the web client is the browser's Web Speech API."""
from google.genai import types
from tenacity import retry, stop_after_attempt, wait_exponential
from app.agent.llm import _get_client
from app.core.config import get_settings


@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=0.5, max=3), reraise=True)
def transcribe(audio: bytes, mime: str) -> str:
    res = _get_client().models.generate_content(
        model=get_settings().asr_model,
        contents=[types.Part.from_bytes(data=audio, mime_type=mime),
                  "Transcribe this audio verbatim. Output only the transcript, nothing else."])
    return (res.text or "").strip()
