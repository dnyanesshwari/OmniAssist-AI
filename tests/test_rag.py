from pathlib import Path

from app.core.config import get_settings
from app.rag.answer import answer_question
from app.rag.ingest import ingest_dir
from app.rag.retrieve import retrieve


def test_ingest_is_idempotent(db, fake_gemini):
    first = ingest_dir(db, get_settings().docs_dir)
    assert all(v.startswith("ingested") for v in first.values())
    second = ingest_dir(db, get_settings().docs_dir)
    assert set(second.values()) == {"unchanged"}


def test_retrieval_finds_right_document(db, fake_gemini):
    ingest_dir(db, get_settings().docs_dir)
    hits = retrieve(db, "how much is the cancellation charge less than 2 hours before")
    assert hits[0].filename == "cancellation_policy.md"
    hits = retrieve(db, "warranty on spare parts 90 days")
    assert hits[0].filename == "warranty_policy.md"


def test_answer_has_citations(db, fake_gemini):
    ingest_dir(db, get_settings().docs_dir)
    a = answer_question(db, "what is the cancellation charge within 2 hours of the appointment?")
    assert not a.abstained and a.citations
    assert a.citations[0]["filename"] and a.citations[0]["snippet"]


def test_abstains_when_nothing_relevant(db, fake_gemini, monkeypatch):
    ingest_dir(db, get_settings().docs_dir)
    monkeypatch.setattr(get_settings(), "rag_min_similarity", 0.6)
    a = answer_question(db, "zzz quantum chromodynamics lattice gauge")
    assert a.abstained and not a.citations


def test_uncited_llm_output_is_rejected(db, fake_gemini, monkeypatch):
    from app.rag import answer as m
    ingest_dir(db, get_settings().docs_dir)
    monkeypatch.setattr(m, "_generate", lambda q, c: "Sure, it is free!")  # no [n] markers
    a = answer_question(db, "cancellation charge within 2 hours")
    assert a.abstained
