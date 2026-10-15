"""Ingest .md / .txt / .pdf files into documents + document_chunks (idempotent by sha256)."""
import hashlib
import sys
from pathlib import Path
from pypdf import PdfReader
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.db.models import Document, DocumentChunk
from app.db.session import SessionLocal
from app.rag import embed
from app.rag.chunk import Chunk, chunk_document


def _load(path: Path) -> list[Chunk]:
    if path.suffix.lower() == ".pdf":
        chunks: list[Chunk] = []
        for i, page in enumerate(PdfReader(str(path)).pages, start=1):
            chunks.extend(chunk_document(page.extract_text() or "", page=i))
        return chunks
    return chunk_document(path.read_text(encoding="utf-8"))


def _title(path: Path) -> str:
    if path.suffix.lower() in {".md", ".txt"}:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                return line[2:].strip()
    return path.stem.replace("_", " ").title()


def ingest_file(db: Session, path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    existing = db.scalar(select(Document).where(Document.filename == path.name))
    if existing and existing.sha256 == digest:
        return "unchanged"
    if existing:
        db.delete(existing)
        db.flush()
    chunks = _load(path)
    if not chunks:
        return "empty"
    vectors = embed.embed_documents([c.content for c in chunks])
    doc = Document(title=_title(path), filename=path.name, sha256=digest)
    doc.chunks = [
        DocumentChunk(chunk_index=i, section=c.section, page=c.page, content=c.content, embedding=v)
        for i, (c, v) in enumerate(zip(chunks, vectors))
    ]
    db.add(doc)
    db.commit()
    return f"ingested {len(chunks)} chunks"


def ingest_dir(db: Session, directory: str | None = None) -> dict[str, str]:
    d = Path(directory or get_settings().docs_dir)
    return {p.name: ingest_file(db, p) for p in sorted(d.iterdir())
            if p.suffix.lower() in {".md", ".txt", ".pdf"}}


if __name__ == "__main__":
    with SessionLocal() as db:
        for name, status in ingest_dir(db, sys.argv[1] if len(sys.argv) > 1 else None).items():
            print(f"{name}: {status}")
