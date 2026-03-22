from ela_pipeline.dataset.book_extraction.engine import BookTextPayload
from ela_pipeline.dataset.book_extraction.english_grammar_in_use_adapter import extract_english_grammar_in_use_rows


def test_english_grammar_in_use_adapter_extracts_unit_explanations_before_exercises():
    payload = BookTextPayload(
        source_path="/tmp/English Grammar in Use 5th Edition - 2019.pdf",
        parser_name="pdf",
        format="pdf",
        text="""
Contents
To the student

Unit
52 Question tags (do you? isn’t it? etc.)
A
Question tags are formed using an auxiliary or a form of be.
You didn’t know I was an artist, did you?

B
Question tags can also be used to show your reaction.
Oh, he wants us to make films as well, does he?

Exercises
52.1 Complete the sentences.

Unit
42 Passive 1 (is done / was done)
A
This house was built in 1981.
When we use the passive, we say what happens to the subject.

Exercises
42.1 Complete the sentences.
""",
    )

    rows = extract_english_grammar_in_use_rows(payload)
    assert rows
    assert any(row.topic_key == "question_tags" for row in rows)
    assert any(row.topic_key == "passive_voice" for row in rows)
    assert not any("complete the sentences" in row.text.lower() for row in rows)
