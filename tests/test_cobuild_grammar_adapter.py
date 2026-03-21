from ela_pipeline.dataset.book_extraction.cobuild_grammar_adapter import extract_cobuild_grammar_rows
from ela_pipeline.dataset.book_extraction.engine import BookTextPayload


def test_cobuild_grammar_adapter_extracts_main_topic_rows_and_skips_supplement():
    prefix = "\n" * 22410
    payload = BookTextPayload(
        source_path="/tmp/COBUILD English Grammar. NEW 4th edition - (Collins COBUILD Grammar) - 2017.pdf",
        parser_name="pdf",
        format="pdf",
        text=prefix
        + """
Introduction
This grammar is suitable for advanced learners.

How to use this Grammar
The book is organized into chapters and sections.

Using modals

Modal verbs are used with the base form of the verb.
You can use will to make predictions.

Question tags

Question tags are formed using an auxiliary or a form of be.
You're coming, aren't you?

The grammar of business English

The passive is often used to describe processes.
The order was processed yesterday.
""",
    )

    rows = extract_cobuild_grammar_rows(payload)

    assert rows
    assert any(row.topic_key == "modal" for row in rows)
    assert any(row.topic_key == "question_tags" for row in rows)
    assert not any("business english" in row.text.lower() for row in rows)
