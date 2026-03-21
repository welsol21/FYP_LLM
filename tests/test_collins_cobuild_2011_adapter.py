from ela_pipeline.dataset.book_extraction.collins_cobuild_2011_adapter import extract_collins_cobuild_2011_rows
from ela_pipeline.dataset.book_extraction.engine import BookTextPayload


def test_collins_cobuild_2011_adapter_extracts_main_topics_and_skips_supplement():
    prefix = "\n" * 20720
    payload = BookTextPayload(
        source_path="/tmp/Collins Cobuild English Grammar - 2011.pdf",
        parser_name="pdf",
        format="pdf",
        text=prefix
        + """
Introduction
This grammar explains how English works in real use.

Making a statement into a question: question tags
Question tags are formed using an auxiliary or a form of be or do.
You didn't know I was an artist, did you?

Using modals
Modals are sometimes called modal verbs or modal auxiliaries.
You can use will to make predictions.

The grammar of business English
The passive is often used in business writing.
The order was processed yesterday.
""",
    )

    rows = extract_collins_cobuild_2011_rows(payload)

    assert rows
    assert any(row.topic_key == "question_tags" for row in rows)
    assert any(row.topic_key == "modal" for row in rows)
    assert not any("business english" in row.text.lower() for row in rows)
