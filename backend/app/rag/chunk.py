"""Cleaning + section-aware, sentence-safe chunking."""
import re
from dataclasses import dataclass


@dataclass
class Chunk:
    content: str
    section: str | None = None
    page: int | None = None


def clean_text(text: str) -> str:
    text = text.replace("\r", "")
    text = re.sub(r"-\n(?=[a-z])", "", text)          # de-hyphenate PDF line breaks
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _split_sentences(par: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", par) if s]


def split_sections(text: str) -> list[tuple[str | None, str]]:
    """Split markdown-ish text on headings -> [(heading, body)]."""
    sections, heading, buf = [], None, []
    for line in text.split("\n"):
        m = re.match(r"^#{1,4}\s+(.*)", line)
        if m:
            if "".join(buf).strip():
                sections.append((heading, "\n".join(buf).strip()))
            heading, buf = m.group(1).strip(), []
        else:
            buf.append(line)
    if "".join(buf).strip():
        sections.append((heading, "\n".join(buf).strip()))
    return sections


def chunk_body(body: str, max_chars: int = 900, overlap: int = 120) -> list[str]:
    """Pack paragraphs (then sentences) into <=max_chars chunks with a small sentence overlap."""
    units: list[str] = []
    for par in re.split(r"\n\s*\n", body):
        par = par.strip()
        if not par:
            continue
        if len(par) <= max_chars:
            units.append(par)
        else:
            units.extend(_split_sentences(par))
    chunks, cur = [], ""
    for u in units:
        if cur and len(cur) + len(u) + 1 > max_chars:
            chunks.append(cur)
            tail = cur[-overlap:]
            tail = tail[tail.find(" ") + 1:] if overlap and " " in tail else ""
            cur = (tail + " " + u).strip()
        else:
            cur = (cur + "\n" + u).strip() if cur else u
    if cur:
        chunks.append(cur)
    return chunks


def chunk_document(text: str, page: int | None = None, max_chars: int = 900) -> list[Chunk]:
    out: list[Chunk] = []
    for heading, body in split_sections(clean_text(text)):
        for piece in chunk_body(body, max_chars=max_chars):
            content = f"{heading}\n{piece}" if heading else piece  # heading kept in text for embedding context
            out.append(Chunk(content=content, section=heading, page=page))
    return out
