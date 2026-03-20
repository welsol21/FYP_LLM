from ela_pipeline.dataset.book_extraction.engine import BookTextPayload
from ela_pipeline.dataset.book_extraction.handbook_adapter import HandbookAdapterConfig, extract_handbook_rows


def test_handbook_adapter_extracts_explanatory_block():
    payload = BookTextPayload(
        source_path="The Oxford Handbook of English Grammar.pdf",
        parser_name="pdf",
        format="pdf",
        text="""
Relative clauses

Relative clauses are similar except that they obligatorily contain a gap and may have an introductory relative phrase like which or who.

        the book which he was reading
        the book that he was reading
""",
    )

    config = HandbookAdapterConfig(
        name="test_handbook",
        source_markers=("oxford handbook",),
        topic_patterns={"relative_clauses": ("relative clauses", "relative clause")},
    )
    rows = extract_handbook_rows(payload, config)
    assert rows
    assert rows[0].topic_key == "relative_clauses"
    assert "obligatorily contain a gap" in rows[0].text
