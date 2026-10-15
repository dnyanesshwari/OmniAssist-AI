from app.rag.chunk import chunk_body, chunk_document, clean_text


def test_clean_text_dehyphenates_and_collapses():
    assert clean_text("ser-\nvice  now\n\n\n\nok") == "service now\n\nok"


def test_chunks_respect_max_size_and_keep_heading():
    text = "# Title\n\n## Fees\n" + " ".join(f"Sentence number {i} is here." for i in range(80))
    chunks = chunk_document(text, max_chars=300)
    assert len(chunks) > 1
    assert all(len(c.content) <= 300 + 150 for c in chunks)  # heading + overlap allowance
    assert all(c.section == "Fees" and c.content.startswith("Fees") for c in chunks)


def test_short_sections_stay_whole():
    chunks = chunk_document("## A\nOne para.\n\n## B\nTwo para.")
    assert [c.section for c in chunks] == ["A", "B"]


def test_overlap_repeats_tail():
    body = "\n\n".join(["alpha " * 30, "beta " * 30, "gamma " * 30])
    parts = chunk_body(body, max_chars=200, overlap=40)
    assert len(parts) >= 3
