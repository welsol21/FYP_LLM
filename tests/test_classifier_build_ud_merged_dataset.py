import json
import tempfile
import unittest
from pathlib import Path

from ela_pipeline.classifier.build_ud_phase1_dataset import build_merged_ud_dataset


class BuildMergedUDDatasetTests(unittest.TestCase):
    def test_build_merged_ud_dataset_deduplicates_same_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            src1 = Path(tmp) / "src1.jsonl"
            src2 = Path(tmp) / "src2.jsonl"
            rows1 = [
                {
                    "id": "a1",
                    "text": "She walks home.",
                    "cefr_level": "A1",
                    "grammar_classes": ["present_simple_affirmative"],
                    "grammar_evidence": {"dep_signature": ["nsubj", "root"], "pos_signature": ["PRON", "VERB"]},
                    "note_blueprints": {
                        "elementary_text": "e1",
                        "intermediate_text": "i1",
                        "advanced_text": "a1",
                    },
                    "tam_profile": "present_simple",
                    "provenance": {"treebank": "UD_English-EWT"},
                }
            ]
            rows2 = [
                {
                    "id": "b1",
                    "text": "She walks home.",
                    "cefr_level": "A1",
                    "grammar_classes": ["present_simple_affirmative"],
                    "grammar_evidence": {"dep_signature": ["nsubj", "root"], "pos_signature": ["PRON", "VERB"]},
                    "note_blueprints": {
                        "elementary_text": "e1",
                        "intermediate_text": "i1",
                        "advanced_text": "a1",
                    },
                    "tam_profile": "present_simple",
                    "provenance": {"treebank": "UD_English-GUM"},
                }
            ]
            src1.write_text("\n".join(json.dumps(r) for r in rows1) + "\n", encoding="utf-8")
            src2.write_text("\n".join(json.dumps(r) for r in rows2) + "\n", encoding="utf-8")

            out = build_merged_ud_dataset(
                input_paths=[str(src1), str(src2)],
                output_dir=str(Path(tmp) / "out"),
                split="train",
            )
            rows = [
                json.loads(line)
                for line in Path(out["dataset_path"]).read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        self.assertEqual(len(rows), 1)
        self.assertEqual(out["deduplicated_rows"], 1)
        self.assertEqual(rows[0]["text"], "She walks home.")


if __name__ == "__main__":
    unittest.main()
