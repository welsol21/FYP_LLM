from ela_pipeline.dataset.book_extraction.engine import BookTextPayload
from ela_pipeline.dataset.book_extraction.gswe_adapter import extract_gswe_rows


def test_gswe_adapter_extracts_topic_rows_and_skips_notes():
    prefix = "\n" * 15545
    payload = BookTextPayload(
        source_path="/tmp/Grammar of Spoken and Written English - 2021.pdf",
        parser_name="pdf",
        format="pdf",
        text=prefix
        + """
3.13.2.4 Question tags

Question tags are formed with an operator and a personal pronoun.
You're coming, aren't you?

Relative clauses

Relative clauses are used to identify a noun or add descriptive information.
the woman who called yesterday

Notes 1139

Passives across syntactic positions and registers
Passives are common in academic prose.
""",
    )

    rows = extract_gswe_rows(payload)

    assert rows
    assert any(row.topic_key == "question_tags" for row in rows)
    assert any(row.topic_key == "relative_clauses" for row in rows)
    assert not any("notes 1139" in row.text.lower() for row in rows)
