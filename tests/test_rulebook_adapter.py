from ela_pipeline.dataset.book_extraction.engine import BookTextPayload
from ela_pipeline.dataset.book_extraction.oxford_dictionary_adapter import (
    OXFORD_DICTIONARY_CONFIG,
    extract_oxford_dictionary_rows,
)


def test_rulebook_adapter_does_not_split_false_inline_sentence_fragments_into_heads():
    payload = BookTextPayload(
        source_path="/tmp/The Oxford Dictionary of English Grammar.pdf",
        parser_name="plain_text",
        format="txt",
        text="\n".join(
            [
                "Organization",
                "Entries are alphabetical.",
                "",
                "A",
                "abbreviated",
                "Shortened or contracted so that a part stands for the whole.",
                "This term is used to designate language in which words inessential to the message are omitted.",
                "conversation. Here the subject and part of the verb are often omitted.",
                "constraints. For example, there is no need for the missing words to be recoverable.",
                "acquisition Linguistics. The process of learning a language.",
            ]
        ),
        metadata={"title": "The Oxford Dictionary of English Grammar"},
    )

    rows = extract_oxford_dictionary_rows(payload)
    heads = {row.entry_head for row in rows if row.row_type == "dictionary_entry"}

    assert "abbreviated" in heads
    assert "conversation." not in heads
    assert "constraints." not in heads
    assert "acquisition Linguistics." not in heads


def test_rulebook_adapter_keeps_example_lines_inside_current_entry_after_example_marker():
    payload = BookTextPayload(
        source_path="/tmp/The Oxford Dictionary of English Grammar.pdf",
        parser_name="plain_text",
        format="txt",
        text="\n".join(
            [
                "Organization",
                "Entries are alphabetical.",
                "",
                "A",
                "abbreviated",
                "Shortened or contracted so that a part stands for the whole.",
                "For example:",
                "See you soon",
                "Back at 5",
                "Contains natural herb extracts",
                "abbreviation",
                "A shortened form of a word or phrase.",
            ]
        ),
        metadata={"title": "The Oxford Dictionary of English Grammar"},
    )

    rows = extract_oxford_dictionary_rows(payload)
    heads = [row.entry_head for row in rows if row.row_type == "dictionary_entry"]

    assert "abbreviated" in heads
    assert "abbreviation" in heads
    assert "See you soon" not in heads
    assert "Back at 5" not in heads
    assert "Contains natural herb extracts" not in heads
