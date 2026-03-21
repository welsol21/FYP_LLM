from ela_pipeline.dataset.extract_english_for_everyone_practice_ocr_pairs import (
    _extract_examples_from_page,
    _extract_heading_and_rule,
)
from ela_pipeline.parse.spacy_parser import load_nlp


def test_extract_heading_and_rule_from_ocr_page():
    lines = [
        "The present simple",
        "The present simple is used to make simple statements",
        "of fact, to talk about things that happen repeatedly,",
        "and to describe things that are always true.",
        "FILL IN THE GAPS BY PUTTING THE VERBS IN THE PRESENT SIMPLE",
    ]

    heading, rule = _extract_heading_and_rule(lines) or ("", "")

    assert heading == "The present simple"
    assert "happen repeatedly" in rule


def test_extract_examples_from_ocr_page_prefers_answered_examples():
    nlp = load_nlp("en_core_web_sm")
    page_text = """
The present simple is used to make simple statements
of fact, to talk about things that happen repeatedly,
and to describe things that are always true.
1.1 FILL IN THE GAPS BY PUTTING THE VERBS IN THE PRESENT SIMPLE
Jessica walks (walk) around the park every day at lunchtime.
Tony (make) a huge breakfast for his family on Sundays.
1.2 MARK THE SENTENCES THAT ARE CORRECT
Steve usually finishes work at 5pm.
Steve usually finishs work at 5pm.
"""

    examples = _extract_examples_from_page(page_text, nlp=nlp)

    assert any(item["context_text"] == "Jessica walks around the park every day at lunchtime." for item in examples)
    assert any(item["context_text"] == "Steve usually finishes work at 5pm." for item in examples)
    assert not any(item["context_text"] == "Steve usually finishs work at 5pm." for item in examples)
    assert not any(item["context_text"] == "Tony a huge breakfast for his family on Sundays." for item in examples)
    assert not any(item["context_text"] == "We sometimes tennis with our friends on Saturday mornings." for item in examples)


def test_extract_heading_and_rule_rejects_non_heading_exercise_page():
    lines = [
        'O 1.3 FILL IN THE GAPS USING "AM,"',
        'jo M8 "15" OR "ARE"',
        "They___are__ here for the party. He___has a lot of homework to do.",
        "@ Vicky my eldest child. @ Jennifer Abbie's bag.",
    ]

    assert _extract_heading_and_rule(lines) is None


def test_extract_examples_keeps_filled_underscore_examples_and_drops_bad_gap_lines():
    nlp = load_nlp("en_core_web_sm")
    page_text = """
The present simple is used to make simple statements of fact.
They___are__ here for the party. He___has a lot of homework to do.
My cousin (start) work at 6am every morning.
We sometimes (play) tennis with our friends on Saturday mornings.
"""

    examples = _extract_examples_from_page(page_text, nlp=nlp)

    assert any(item["context_text"] == "They are here for the party." for item in examples)
    assert any(item["context_text"] == "He has a lot of homework to do." for item in examples)
    assert not any(item["context_text"] == "My cousin work at 6am every morning." for item in examples)
    assert not any(item["context_text"] == "We sometimes tennis with our friends on Saturday mornings." for item in examples)


def test_extract_examples_skips_rule_text_and_incomplete_question_fragments():
    nlp = load_nlp("en_core_web_sm")
    page_text = """
In spoken English, small questions are often added to
the ends of sentences. These are called question tags,
and they are most often used to invite someone to agree.
39.1 MATCH THE BEGINNINGS OF THE SENTENCES TO THE CORRECT QUESTION TAGS
have a garage?
Are you a chef?
do they know your address?
"""

    examples = _extract_examples_from_page(page_text, nlp=nlp)
    contexts = {item["context_text"] for item in examples}

    assert "they are most often used to invite someone to agree." not in contexts
    assert "have a garage?" not in contexts
    assert "Are you a chef?" in contexts
    assert "do they know your address?" in contexts
