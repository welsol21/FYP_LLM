from ela_pipeline.dataset.filter_note_context_pairs import build_clean_note_context_pairs


def test_clean_pair_filter_keeps_good_examples_and_drops_obvious_errors():
    rows = [
        {"context_text": "Selma goes shopping after work.", "topic_key": ""},
        {"context_text": "Greg workes in a factory.", "topic_key": ""},
        {"context_text": "He does not likes baseball.", "topic_key": ""},
        {"context_text": "Diana doesn't have a computer.", "topic_key": ""},
        {"context_text": "They isn't from China.", "topic_key": ""},
        {"context_text": "do they know your address?", "topic_key": ""},
        {"context_text": "have a garage?", "topic_key": ""},
        {"context_text": "Phil don't drive a car.", "topic_key": ""},
        {"context_text": "In this", "topic_key": "", "pair_method": "rulebook_source_first"},
        {"context_text": "to use.", "topic_key": "", "pair_method": "rulebook_source_first"},
        {"context_text": "with no name", "topic_key": "", "pair_method": "rulebook_source_first"},
        {"context_text": "Native speakers may disagree over whether a particular utterance is", "topic_key": "", "pair_method": "rulebook_source_first"},
        {"context_text": "QUIRK Characters in Dickens can use an’t or ain’t for ‘isn’t’ without", "topic_key": "", "pair_method": "rulebook_source_first"},
        {"context_text": "Its four major", "topic_key": "", "pair_method": "rulebook_source_first"},
        {"context_text": "As the examples show, the adjectival head may appear early or later.", "topic_key": "", "pair_method": "rulebook_source_first"},
        {"context_text": "“history” begins with a consonant sound).", "topic_key": "", "pair_method": "rulebook_source_first"},
    ]

    kept, report = build_clean_note_context_pairs(rows)
    contexts = {row["context_text"] for row in kept}

    assert "Selma goes shopping after work." in contexts
    assert "Diana doesn't have a computer." in contexts
    assert "do they know your address?" in contexts
    assert "Greg workes in a factory." not in contexts
    assert "He does not likes baseball." not in contexts
    assert "They isn't from China." not in contexts
    assert "have a garage?" not in contexts
    assert "Phil don't drive a car." not in contexts
    assert "In this" not in contexts
    assert "to use." not in contexts
    assert "with no name" in contexts
    assert "Native speakers may disagree over whether a particular utterance is" not in contexts
    assert "QUIRK Characters in Dickens can use an’t or ain’t for ‘isn’t’ without" not in contexts
    assert "Its four major" not in contexts
    assert "As the examples show, the adjectival head may appear early or later." not in contexts
    assert "“history” begins with a consonant sound)." not in contexts
    assert report["stats"]["kept_rows"] == 4
