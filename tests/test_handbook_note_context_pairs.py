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
