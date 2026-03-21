from pathlib import Path

from ela_pipeline.dataset.build_handbook_note_context_pairs import build_handbook_note_context_pairs


def test_handbook_pairs_extract_notation_and_context(tmp_path: Path):
    rows_path = tmp_path / "rows.jsonl"
    rows_path.write_text(
        '{"source_path":"book.pdf","row_type":"handbook_snippet","topic_key":"relative_clauses","heading":"Relative clauses","text":"Relative clauses are similar except that they obligatorily contain a gap.\\n\\nThe book which he was reading.\\nThe book that he was reading."}\n',
        encoding="utf-8",
    )

    pairs, report = build_handbook_note_context_pairs(rows_jsonl=str(rows_path))
    assert report["pairs_total"] >= 2
    assert any("obligatorily contain a gap" in row["notation_text"] for row in pairs)
    assert any("The book which he was reading" in row["context_text"] for row in pairs)


def test_handbook_pairs_filter_meta_and_non_matching_topic_contexts(tmp_path: Path):
    rows_path = tmp_path / "rows.jsonl"
    rows_path.write_text(
        '{"source_path":"book.pdf","row_type":"handbook_snippet","topic_key":"passive_voice","heading":"Passive","text":"The passive voice foregrounds the affected participant rather than the doer.\\n\\nHowever, end-focus is not the only ordering principle.\\nKim had a new car.\\nThe lid was lifted by Kim."}\n'
        '{"source_path":"book.pdf","row_type":"handbook_snippet","topic_key":"prepositions","heading":"Prepositions","text":"Prepositions head phrases and take complements.\\n\\nAs noted\\nHe stayed in the house.\\nShe started working."}\n',
        encoding="utf-8",
    )

    pairs, report = build_handbook_note_context_pairs(rows_jsonl=str(rows_path))

    assert report["pairs_total"] == 2
    contexts = {row["context_text"] for row in pairs}
    assert "The lid was lifted by Kim." in contexts
    assert "He stayed in the house." in contexts
    assert "However, end-focus is not the only ordering principle." not in contexts
    assert "Kim had a new car." not in contexts
    assert "As noted" not in contexts
    assert "She started working." not in contexts


def test_handbook_pairs_prioritize_topic_explicit_notation_sentences(tmp_path: Path):
    rows_path = tmp_path / "rows.jsonl"
    rows_path.write_text(
        '{"source_path":"book.pdf","row_type":"handbook_snippet","topic_key":"prepositions","heading":"Prepositions","text":"These constructions are important in the grammar of English. Prepositions head phrases and take complements.\\n\\nHe stayed in the house."}\n',
        encoding="utf-8",
    )

    pairs, _report = build_handbook_note_context_pairs(rows_jsonl=str(rows_path))

    assert pairs
    assert "Prepositions head phrases and take complements." in pairs[0]["notation_text"]


def test_handbook_pairs_strip_teaching_prefixes_and_dialogue_labels(tmp_path: Path):
    rows_path = tmp_path / "rows.jsonl"
    rows_path.write_text(
        '{"source_path":"book.pdf","row_type":"egu_unit_section","topic_key":"modal","heading":"Unit 30 may and might 2","text":"Modal verbs such as may and might express possibility.\\n\\nSo you can say: I may go to Ireland.\\na: What shall we do tonight?\\nb: We could go to the cinema."}\n',
        encoding="utf-8",
    )

    pairs, report = build_handbook_note_context_pairs(rows_jsonl=str(rows_path))

    assert report["pairs_total"] >= 2
    contexts = {row["context_text"] for row in pairs}
    assert "I may go to Ireland." in contexts
    assert "We could go to the cinema." in contexts
    assert "So you can say: I may go to Ireland." not in contexts
    assert "a: What shall we do tonight?" not in contexts
    assert "b: We could go to the cinema." not in contexts


def test_handbook_pairs_reject_all_caps_workbook_fragments(tmp_path: Path):
    rows_path = tmp_path / "rows.jsonl"
    rows_path.write_text(
        "{\"source_path\":\"book.pdf\",\"row_type\":\"practice_book_section\",\"topic_key\":\"modal\",\"heading\":\"Obligations\",\"text\":\"Obligations In English, must and have to express obligation.\\n\\nMUST NOT\\nDON'T HAVE TO\"}\n",
        encoding="utf-8",
    )

    pairs, report = build_handbook_note_context_pairs(rows_jsonl=str(rows_path))

    assert report["pairs_total"] == 0


def test_handbook_pairs_source_first_handles_rows_without_topic_key(tmp_path: Path):
    rows_path = tmp_path / "rows.jsonl"
    rows_path.write_text(
        '{"source_path":"book.pdf","row_type":"egt_article_window","topic_key":"","heading":"A/an and the","anchor":"A/an and the","text":"A/an and the are articles. They are a type of determiner.\\n\\nDo you have a car?"}\n',
        encoding="utf-8",
    )

    pairs, report = build_handbook_note_context_pairs(rows_jsonl=str(rows_path), source_first=True)

    assert report["pairs_total"] == 1
    assert pairs[0]["notation_text"] == "A/an and the are articles. They are a type of determiner."
    assert pairs[0]["context_text"] == "Do you have a car?"
    assert pairs[0]["pair_method"] == "handbook_window_source_first"
