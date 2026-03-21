from ela_pipeline.dataset.book_extraction.english_grammar_today_adapter import extract_english_grammar_today_rows
from ela_pipeline.dataset.book_extraction.engine import BookTextPayload


def test_english_grammar_today_adapter_extracts_front_matter_and_article_windows():
    payload = BookTextPayload(
        source_path="/tmp/Ronald Carter - English Grammar Today - 2011.pdf",
        parser_name="pdf",
        format="pdf",
        text="""
Introduction
English Grammar Today is a reference book with accompanying CD-ROM.

Organisation
The book has a simple A-Z structure and cross references.

Typical errors
We show typical learner errors at the end of many entries.

Examples in context
Some examples give context labels in brackets.

Standard and non-standard
We explain standard and non-standard forms.

Correct English
Not: But we've still enjoyed our holiday.

Symbols used in English Grammar Today
> = Cross reference

\f
A/an and the 1

A/an and the: meaning

A/an and the are articles. They are a type of determiner.
Do you have a car?

\f
Question tags 343

Question tags

Question tags turn statements into yes-no questions.
It's cold today, isn't it?

\f
Relative clauses 307

Relative clauses

Relative clauses give us more information about someone or something.
the book that I bought yesterday

Glossary
Clause
""",
    )

    rows = extract_english_grammar_today_rows(payload)
    row_types = [row.row_type for row in rows]

    assert "organisation_rule" in row_types
    assert "typical_errors_rule" in row_types

    question_rows = [row for row in rows if row.topic_key == "question_tags"]
    relative_rows = [row for row in rows if row.topic_key == "relative_clauses"]

    assert question_rows
    assert relative_rows
    assert any("yes-no questions" in row.text for row in question_rows)
    assert any("the book that I bought yesterday" in row.text for row in relative_rows)
    assert any(row.heading == "A/an and the" and row.topic_key == "" for row in rows)
