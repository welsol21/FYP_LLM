import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ela_pipeline.runtime.media_pipeline import run_media_pipeline


class RuntimeMediaPipelineTests(unittest.TestCase):
    def test_text_pipeline_builds_sentences_and_contract_nodes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "sample.txt"
            source.write_text("She trusted him. Before making the decision.", encoding="utf-8")

            result = run_media_pipeline(source_path=str(source))
            self.assertEqual(result.source_type, "text")
            self.assertIn("She trusted him.", result.full_text)
            self.assertEqual(len(result.media_sentences), 2)
            self.assertEqual(len(result.contract_sentences), 2)
            self.assertEqual(result.contract_sentences[0]["sentence_node"]["type"], "Sentence")
            sentence_node = result.contract_sentences[0]["sentence_node"]
            self.assertIsInstance(sentence_node.get("linguistic_notes"), list)
            self.assertTrue(sentence_node.get("translation", {}).get("text"))
            self.assertIn("phonetic", sentence_node)
            media_row = result.media_sentences[0]
            self.assertIn("start_ms", media_row)
            self.assertIn("end_ms", media_row)
            self.assertIn("units", media_row)
            self.assertIn("text_eng", media_row)
            self.assertIn("text_ru", media_row)

    def test_audio_pipeline_uses_asr_extraction_chunks(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            media = Path(tmpdir) / "sample.mp3"
            media.write_bytes(b"fake-audio")
            with patch(
                "ela_pipeline.runtime.media_pipeline._extract_text_and_sentence_chunks",
                return_value=(
                    "This is transcript text. It has two sentences.",
                    [
                        {"sentence_text": "This is transcript text.", "start_sec": 0.0, "end_sec": 1.2},
                        {"sentence_text": "It has two sentences.", "start_sec": 1.3, "end_sec": 2.7},
                    ],
                ),
            ):
                result = run_media_pipeline(source_path=str(media))
            self.assertEqual(result.source_type, "audio")
            self.assertEqual(len(result.media_sentences), 2)
            self.assertEqual(result.media_sentences[0]["start_ms"], 0)
            self.assertEqual(result.media_sentences[1]["start_ms"], 1300)

    def test_pipeline_uses_external_sentence_contract_builder(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "sample.txt"
            source.write_text("She trusted him. Before making the decision.", encoding="utf-8")

            calls: list[tuple[str, int]] = []

            def builder(*, sentence_text: str, sentence_idx: int):
                calls.append((sentence_text, sentence_idx))
                return {
                    "sentence_text": sentence_text,
                    "sentence_hash": f"h-{sentence_idx}",
                    "sentence_node": {
                        "type": "Sentence",
                        "node_id": f"n-{sentence_idx}",
                        "content": sentence_text,
                        "linguistic_elements": [],
                    },
                }

            result = run_media_pipeline(source_path=str(source), sentence_contract_builder=builder)
            self.assertEqual(len(calls), 2)
            self.assertEqual(calls[0][0], "She trusted him.")
            self.assertEqual(calls[1][1], 1)
            self.assertEqual(result.contract_sentences[0]["sentence_hash"], "h-0")
            self.assertEqual(result.contract_sentences[1]["sentence_node"]["node_id"], "n-1")
            self.assertEqual(result.media_sentences[0]["text_eng"], "She trusted him.")
            self.assertEqual(result.media_sentences[0]["text_ru"], "")


if __name__ == "__main__":
    unittest.main()
