from ela_pipeline.dataset.book_extraction.engine import BookTextPayload
from ela_pipeline.dataset.book_extraction.english_for_everyone_practice_adapter import (
    extract_english_for_everyone_practice_rows,
)


def test_english_for_everyone_practice_adapter_extracts_sections_and_stops_before_answers():
    prefix = "\n" * 1342
    payload = BookTextPayload(
        source_path="/tmp/Booth Thomas - English for Everyone. English Grammar Guide. Practice Book - 2019.pdf",
        parser_name="pdf",
        format="pdf",
        text=prefix
        + """
The passive
In most sentences, the subject carries out an action and the object receives it.
MATCH THE PICTURES TO THE CORRECT SENTENCES
REWRITE THE SENTENCES, CORRECTING THE ERRORS

Question tags
In spoken English, small questions are often added to the ends of sentences.
ADD QUESTION TAGS TO THESE SENTENCES

Answers
This should never be included.
""",
    )

    rows = extract_english_for_everyone_practice_rows(payload)

    assert rows
    assert any(row.topic_key == "passive_voice" for row in rows)
    assert any(row.topic_key == "question_tags" for row in rows)
    assert not any("this should never be included" in row.text.lower() for row in rows)
