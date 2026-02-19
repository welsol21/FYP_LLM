import tempfile
import unittest
from pathlib import Path

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

    def test_audio_pipeline_uses_sidecar_transcript(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            media = Path(tmpdir) / "sample.mp3"
            media.write_bytes(b"fake-audio")
            sidecar = Path(tmpdir) / "sample.mp3.txt"
            sidecar.write_text("This is transcript text. It has two sentences.", encoding="utf-8")

            result = run_media_pipeline(source_path=str(media))
            self.assertEqual(result.source_type, "audio")
            self.assertEqual(len(result.media_sentences), 2)

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


if __name__ == "__main__":
    unittest.main()
