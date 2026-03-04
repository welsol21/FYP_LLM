import json
import tempfile
import unittest
from pathlib import Path

from ela_pipeline.classifier.build_ud_phase1_dataset import build_phase1_dataset_from_ud


class BuildUDGenreFilterTests(unittest.TestCase):
    def test_build_phase1_dataset_from_ud_filters_by_allowed_genre(self):
        rows = [
            {
                "id": "train-1",
                "text": "The study had shown clear results.",
                "cefr_level": "B2",
                "grammar_classes": ["past_perfect"],
                "tam_profile": "past_perfect",
                "grammar_evidence": {"dep_signature": ["nsubj", "aux", "root"], "pos_signature": ["DET", "NOUN", "AUX", "VERB"]},
                "note_blueprints": {
                    "elementary_text": "e",
                    "intermediate_text": "i",
                    "advanced_text": "a",
                },
                "provenance": {"treebank": "UD_English-GUM", "split": "train", "genre": "academic"},
            },
            {
                "id": "train-2",
                "text": "We had left before dawn.",
                "cefr_level": "B2",
                "grammar_classes": ["past_perfect"],
                "tam_profile": "past_perfect",
                "grammar_evidence": {"dep_signature": ["nsubj", "aux", "root"], "pos_signature": ["PRON", "AUX", "VERB"]},
                "note_blueprints": {
                    "elementary_text": "e",
                    "intermediate_text": "i",
                    "advanced_text": "a",
                },
                "provenance": {"treebank": "UD_English-GUM", "split": "train", "genre": "conversation"},
            },
        ]

        with tempfile.TemporaryDirectory() as tmp:
            result = build_phase1_dataset_from_ud(
                input_paths=[],
                output_dir=str(Path(tmp) / "out"),
                treebank="UD_English-GUM",
                split="train",
                allowed_genres=["academic"],
                prebuilt_rows=rows,
            )
            exported_rows = [
                json.loads(line)
                for line in Path(result["dataset_path"]).read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        self.assertEqual(result["filtered_out_rows"], 1)
        self.assertEqual(result["accepted_rows"], 1)
        self.assertEqual(exported_rows[0]["provenance"]["genre"], "academic")
        self.assertEqual(result["allowed_genres"], ["academic"])


if __name__ == "__main__":
    unittest.main()
