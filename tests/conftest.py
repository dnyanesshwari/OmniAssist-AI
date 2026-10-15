import hashlib
import math
import os
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://omni:change_me@localhost:5432/omniassist_test")
os.environ["DOCS_DIR"] = str(ROOT / "data" / "documents")

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db.session import SessionLocal, engine  # noqa: E402
from app.rag import answer as answer_mod, embed  # noqa: E402
from scripts.seed import seed  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _migrate():
    with engine.begin() as c:
        c.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    cfg = Config(str(ROOT / "backend" / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "backend" / "alembic"))
    command.upgrade(cfg, "head")


@pytest.fixture(autouse=True)
def _clean():
    with engine.begin() as c:
        c.execute(text("TRUNCATE audit_events, handoff_tickets, messages, conversations, appointments, "
                       "technician_services, technicians, services, document_chunks, documents, customers "
                       "RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture
def db():
    with SessionLocal() as s:
        yield s


@pytest.fixture
def seeded(db):
    seed(db)
    return db


@pytest.fixture
def client():
    from app.main import app
    return TestClient(app)


# ---- deterministic fake Gemini: hashed bag-of-words embeddings + extractive "LLM" ----
def _fake_vec(text_: str, dim: int = 768) -> list[float]:
    v = [0.0] * dim
    for w in re.findall(r"[a-z0-9₹]+", text_.lower()):
        v[int(hashlib.md5(w.encode()).hexdigest(), 16) % dim] += 1.0
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


@pytest.fixture
def fake_gemini(monkeypatch):
    monkeypatch.setattr(embed, "embed_documents", lambda texts, batch=50: [_fake_vec(t) for t in texts])
    monkeypatch.setattr(embed, "embed_query", lambda t: _fake_vec(t))
    # "LLM": answers by citing the first context passage, or abstains if told nothing relevant
    monkeypatch.setattr(answer_mod, "_generate",
                        lambda question, context: "Based on the policy documents. [1]")
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "rag_min_similarity", 0.25)
