import math
from google import genai
from google.genai import types
from tenacity import retry, stop_after_attempt, wait_exponential
from app.core.config import get_settings

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = genai.Client(api_key=get_settings().gemini_api_key)
    return _client


def _normalize(v: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, max=10), reraise=True)
def _embed(texts: list[str], task_type: str) -> list[list[float]]:
    s = get_settings()
    res = _get_client().models.embed_content(
        model=s.embedding_model, contents=texts,
        config=types.EmbedContentConfig(task_type=task_type, output_dimensionality=s.embedding_dim),
    )
    return [_normalize(list(e.values)) for e in res.embeddings]


def embed_documents(texts: list[str], batch: int = 50) -> list[list[float]]:
    out: list[list[float]] = []
    for i in range(0, len(texts), batch):
        out.extend(_embed(texts[i:i + batch], "RETRIEVAL_DOCUMENT"))
    return out


def embed_query(text: str) -> list[float]:
    return _embed([text], "RETRIEVAL_QUERY")[0]
