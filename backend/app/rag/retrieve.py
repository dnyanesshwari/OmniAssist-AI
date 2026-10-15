from dataclasses import dataclass
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.db.models import Document, DocumentChunk
from app.rag import embed


@dataclass
class Hit:
    chunk_id: int
    document_id: int
    title: str
    filename: str
    section: str | None
    page: int | None
    content: str
    similarity: float


def retrieve(db: Session, query: str, k: int | None = None) -> list[Hit]:
    k = k or get_settings().rag_top_k
    qv = embed.embed_query(query)
    dist = DocumentChunk.embedding.cosine_distance(qv)
    rows = db.execute(
        select(DocumentChunk, Document, (1 - dist).label("sim"))
        .join(Document, Document.id == DocumentChunk.document_id)
        .order_by(dist).limit(k)
    ).all()
    return [Hit(c.id, d.id, d.title, d.filename, c.section, c.page, c.content, float(sim))
            for c, d, sim in rows]
