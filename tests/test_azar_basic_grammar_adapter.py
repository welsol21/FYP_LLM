from ela_pipeline.dataset.book_extraction.azar_basic_grammar_adapter import extract_azar_basic_grammar_rows
from ela_pipeline.dataset.book_extraction.engine import BookTextPayload


def test_azar_basic_grammar_adapter_extracts_section_before_exercises():
    payload = BookTextPayload(
        source_path="/tmp/Betty Scrampfer Azar - Basic English Grammar, Second Edition - 1996.pdf",
        parser_name="pdf",
        format="pdf",
        text="""
CHAPTER 6

6-16 CLAUSES WITH IF
(a) If it rains tomorrow, we will stay home.
An if-clause begins with if and has a subject and a verb.
The simple present is used in an if-clause to express future time.

EXERCISE 35: Complete the sentences.

CHAPTER 7

7-1 USING CAN
(a) I have some money. I can buy a book.
Can expresses ability and possibility.

EXERCISE 1-ORAL: Make sentences.
""",
    )

    rows = extract_azar_basic_grammar_rows(payload)

    assert len(rows) == 2
    assert rows[0].topic_key == "conditional_sentences"
    assert "if-clause begins with if" in rows[0].text
    assert "EXERCISE" not in rows[0].text
    assert rows[1].topic_key == "modal"
    assert "ability and possibility" in rows[1].text
