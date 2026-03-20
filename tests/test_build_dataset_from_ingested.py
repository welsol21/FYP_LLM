import json
import tempfile
import unittest
from pathlib import Path

from ela_pipeline.dataset.build_dataset_from_ingested import _make_rows


class BuildDatasetFromIngestedTests(unittest.TestCase):
    def test_make_rows_uses_contract_template_prompt_for_sentence_and_phrase(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            nodes_dir = Path(tmpdir)
            (nodes_dir / "sentences.jsonl").write_text(
                json.dumps(
                    {
                        "content": "You called him, didn't you?",
                        "cefr_level": "B1",
                        "tam_construction": "none",
                        "features": {"pos": ["PRON", "VERB"], "dep": ["nsubj", "ROOT"]},
                        "grammar_classes": [{"class_id": "question_tag", "confidence": 0.9}],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (nodes_dir / "phrases.jsonl").write_text(
                json.dumps(
                    {
                        "content": "near the Syrian border",
                        "sentence_text": "American forces killed Shaikh Abdullah al-Ani near the Syrian border.",
                        "part_of_speech": "prepositional phrase",
                        "grammatical_role": "modifier",
                        "cefr_level": "A2",
                        "tam_construction": "none",
                        "features": {"pos": ["ADP", "DET", "ADJ", "NOUN"], "dep": ["prep", "det", "amod", "pobj"]},
                        "grammar_classes": [{"class_id": "prepositional_relation_phrase", "confidence": 0.9}],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (nodes_dir / "words.jsonl").write_text(
                json.dumps(
                    {
                        "content": "trusted",
                        "sentence_text": "She trusted him.",
                        "part_of_speech": "verb",
                        "grammatical_role": "predicate",
                        "features": {"pos": ["VERB"], "tag": ["VBD"], "dep": ["ROOT"], "morph": ["Tense=Past"]},
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            rows, counters = _make_rows(nodes_dir)

        self.assertEqual(counters["rows_emitted"], 3)
        by_level = {row["level"]: row for row in rows}
        self.assertEqual(by_level["Sentence"]["prompt_template_version"], "contract_template_v1")
        self.assertEqual(by_level["Phrase"]["prompt_template_version"], "contract_template_v1")
        self.assertEqual(by_level["Word"]["prompt_template_version"], "v2")
        self.assertIn("write_linguistic_note_from_contract_template", by_level["Sentence"]["input"])
        self.assertIn("write_linguistic_note_from_contract_template", by_level["Phrase"]["input"])
        self.assertIn("template_version: v2", by_level["Word"]["input"])


if __name__ == "__main__":
    unittest.main()
