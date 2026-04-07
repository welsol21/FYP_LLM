import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from ela_pipeline.runtime.media_pipeline import _extract_text_and_sentence_chunks, run_media_pipeline


class RuntimeMediaPipelineTests(unittest.TestCase):
    @staticmethod
    def _builder(*, sentence_text: str, sentence_idx: int):
        return {
            "sentence_text": sentence_text,
            "sentence_hash": f"h-{sentence_idx}",
            "sentence_node": {
                "type": "Sentence",
                "node_id": f"n-{sentence_idx}",
                "content": sentence_text,
                "linguistic_elements": [],
                "linguistic_notes": {"elementary": "", "intermediate": "", "advanced": ""},
                "translations": {"m2m100": {"text": sentence_text}},
                "phonetic": {"uk": "", "us": ""},
            },
        }

    def test_pipeline_requires_external_sentence_contract_builder(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "sample.txt"
            source.write_text("She trusted him.", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "sentence_contract_builder is required"):
                run_media_pipeline(source_path=str(source))

    def test_text_pipeline_builds_sentences_and_contract_nodes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "sample.txt"
            source.write_text("She trusted him. Before making the decision.", encoding="utf-8")

            result = run_media_pipeline(source_path=str(source), sentence_contract_builder=self._builder)
            self.assertEqual(result.source_type, "text")
            self.assertIn("She trusted him.", result.full_text)
            self.assertEqual(len(result.media_sentences), 2)
            self.assertEqual(len(result.contract_sentences), 2)
            self.assertEqual(result.contract_sentences[0]["sentence_node"]["type"], "Sentence")
            sentence_node = result.contract_sentences[0]["sentence_node"]
            self.assertIsInstance(sentence_node.get("linguistic_notes"), dict)
            self.assertTrue(sentence_node.get("translations", {}).get("m2m100", {}).get("text"))
            self.assertIn("phonetic", sentence_node)
            media_row = result.media_sentences[0]
            self.assertIn("start_ms", media_row)
            self.assertIn("end_ms", media_row)
            self.assertIn("units", media_row)
            self.assertIn("text_eng", media_row)
            self.assertIn("text_ru", media_row)

    def test_text_pipeline_skips_metadata_and_heading_lines(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "sample.txt"
            source.write_text(
                (
                    "The Voice of Reason One.\n"
                    "The Last Wish, written by Andrei Sapkowski, translated from the Polish by Danusia Stock and read by Peter Kenny.\n"
                    "She trusted him.\n"
                ),
                encoding="utf-8",
            )

            result = run_media_pipeline(source_path=str(source), sentence_contract_builder=self._builder)
            self.assertEqual(len(result.media_sentences), 1)
            self.assertEqual(result.media_sentences[0]["sentence_text"], "She trusted him.")

    def test_audio_pipeline_skips_metadata_like_asr_segments(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            media = Path(tmpdir) / "sample.mp3"
            media.write_bytes(b"fake-audio")
            with patch(
                "ela_pipeline.runtime.media_pipeline._extract_text_and_sentence_chunks",
                return_value=(
                    (
                        "The Voice of Reason One. "
                        "The Last Wish, written by Andrei Sapkowski, translated from the Polish by Danusia Stock and read by Peter Kenny. "
                        "She trusted him."
                    ),
                    [
                        {"sentence_text": "The Voice of Reason One.", "start_sec": 0.0, "end_sec": 0.6},
                        {
                            "sentence_text": "The Last Wish, written by Andrei Sapkowski, translated from the Polish by Danusia Stock and read by Peter Kenny.",
                            "start_sec": 0.7,
                            "end_sec": 2.2,
                        },
                        {"sentence_text": "She trusted him.", "start_sec": 2.3, "end_sec": 3.2},
                    ],
                ),
            ):
                result = run_media_pipeline(source_path=str(media), sentence_contract_builder=self._builder)
            self.assertEqual(len(result.media_sentences), 1)
            self.assertEqual(result.media_sentences[0]["sentence_text"], "She trusted him.")

    def test_audio_pipeline_fallbacks_when_metadata_filter_removes_all_sentences(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            media = Path(tmpdir) / "sample.mp3"
            media.write_bytes(b"fake-audio")
            with patch(
                "ela_pipeline.runtime.media_pipeline._extract_text_and_sentence_chunks",
                return_value=(
                    "The Last Wish, translated by Danusia Stock.",
                    [
                        {
                            "sentence_text": "The Last Wish, translated by Danusia Stock.",
                            "start_sec": 0.0,
                            "end_sec": 1.2,
                        },
                    ],
                ),
            ):
                result = run_media_pipeline(source_path=str(media), sentence_contract_builder=self._builder)
            self.assertEqual(len(result.media_sentences), 1)
            self.assertEqual(
                result.media_sentences[0]["sentence_text"],
                "The Last Wish, translated by Danusia Stock.",
            )

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
                result = run_media_pipeline(source_path=str(media), sentence_contract_builder=self._builder)
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

    def test_audio_asr_fails_fast_when_runtime_downloads_disabled_and_model_not_bundled(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            media = Path(tmpdir) / "sample.mp3"
            media.write_bytes(b"fake-audio")
            with patch.dict(
                "os.environ",
                {
                    "ELA_MEDIA_DISABLE_RUNTIME_DOWNLOADS": "1",
                    "ELA_MEDIA_ASR_MODEL": "base",
                    "ELA_MEDIA_ASR_CACHE_DIR": str(Path(tmpdir) / "whisper_cache"),
                },
                clear=False,
            ):
                with self.assertRaises(RuntimeError):
                    _extract_text_and_sentence_chunks(media, "audio")

    def test_audio_extraction_groups_word_timestamps_into_sentence_windows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            media = Path(tmpdir) / "sample.mp3"
            media.write_bytes(b"fake-audio")
            mock_result = {
                "text": "Mr. Holmes spoke. Then paused.",
                "segments": [
                    {
                        "start": 0.0,
                        "end": 2.0,
                        "words": [
                            {"word": "Mr.", "start": 0.00, "end": 0.18},
                            {"word": "Holmes", "start": 0.20, "end": 0.58},
                            {"word": "spoke.", "start": 0.60, "end": 0.95},
                            {"word": "Then", "start": 1.05, "end": 1.35},
                            {"word": "paused.", "start": 1.36, "end": 1.86},
                        ],
                    },
                ],
            }
            with (
                patch("ela_pipeline.runtime.media_pipeline._get_whisper_model_cached") as mock_model_factory,
                patch("whisper.load_audio", return_value=np.zeros(32_000, dtype=np.float32)),
                patch("ela_pipeline.runtime.media_pipeline._probe_media_duration_seconds", return_value=2.0),
            ):
                mock_model = mock_model_factory.return_value
                mock_model.transcribe.return_value = mock_result
                full_text, chunks = _extract_text_and_sentence_chunks(media, "audio")

            self.assertEqual(full_text, "Mr. Holmes spoke. Then paused.")
            # Reference approach: split at every .?! — "Mr." is its own chunk
            self.assertEqual(len(chunks), 3)
            self.assertEqual(chunks[0]["sentence_text"], "Mr.")
            self.assertEqual(chunks[1]["sentence_text"], "Holmes spoke.")
            self.assertEqual(chunks[2]["sentence_text"], "Then paused.")
            self.assertAlmostEqual(float(chunks[1]["start_sec"]), 0.20, places=2)
            self.assertAlmostEqual(float(chunks[1]["end_sec"]), 0.95, places=2)
            self.assertAlmostEqual(float(chunks[2]["start_sec"]), 1.05, places=2)
            self.assertAlmostEqual(float(chunks[2]["end_sec"]), 1.86, places=2)
            self.assertGreaterEqual(float(chunks[2]["start_sec"]), float(chunks[1]["end_sec"]))
            # Chunks must carry pre-built units
            self.assertIn("units", chunks[1])
            self.assertTrue(len(chunks[1]["units"]) > 0)

            kwargs = mock_model.transcribe.call_args.kwargs
            self.assertTrue(bool(kwargs.get("word_timestamps")))

    def test_audio_pipeline_units_use_whisper_word_level_timestamps(self):
        """Units for each sentence should use actual Whisper word timestamps,
        not evenly-distributed estimates (reference: transcribe_and_translate_windows.py)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            media = Path(tmpdir) / "sample.mp3"
            media.write_bytes(b"fake-audio")
            mock_result = {
                "text": "Holmes spoke. Then paused.",
                "segments": [
                    {
                        "start": 0.0,
                        "end": 2.0,
                        "words": [
                            {"word": "Holmes", "start": 0.10, "end": 0.50},
                            {"word": "spoke.", "start": 0.60, "end": 0.90},
                            {"word": "Then", "start": 1.10, "end": 1.40},
                            {"word": "paused.", "start": 1.50, "end": 1.80},
                        ],
                    },
                ],
            }
            with (
                patch("ela_pipeline.runtime.media_pipeline._get_whisper_model_cached") as mock_model_factory,
                patch("whisper.load_audio", return_value=np.zeros(32_000, dtype=np.float32)),
                patch("ela_pipeline.runtime.media_pipeline._probe_media_duration_seconds", return_value=2.0),
            ):
                mock_model = mock_model_factory.return_value
                mock_model.transcribe.return_value = mock_result
                result = run_media_pipeline(source_path=str(media), sentence_contract_builder=self._builder)

            self.assertEqual(len(result.media_sentences), 2)
            s0_units = result.media_sentences[0]["units"]
            s1_units = result.media_sentences[1]["units"]

            # Sentence 0: "Holmes spoke." — unit timestamps must come from Whisper words
            holmes_unit = next((u for u in s0_units if u["text"] == "Holmes"), None)
            spoke_unit = next((u for u in s0_units if u["text"] == "spoke"), None)
            self.assertIsNotNone(holmes_unit)
            self.assertIsNotNone(spoke_unit)
            self.assertAlmostEqual(holmes_unit["audio"]["origin_start"], 0.10, places=2)
            self.assertAlmostEqual(holmes_unit["audio"]["origin_end"], 0.50, places=2)
            self.assertAlmostEqual(spoke_unit["audio"]["origin_start"], 0.60, places=2)
            self.assertAlmostEqual(spoke_unit["audio"]["origin_end"], 0.90, places=2)

            # Sentence 1: "Then paused." — word timestamps must not bleed from sentence 0
            then_unit = next((u for u in s1_units if u["text"] == "Then"), None)
            self.assertIsNotNone(then_unit)
            self.assertAlmostEqual(then_unit["audio"]["origin_start"], 1.10, places=2)
            self.assertGreaterEqual(then_unit["audio"]["origin_start"], 1.0)

            # Sentence order: s0 must end before s1 starts
            self.assertLessEqual(
                result.media_sentences[0]["end_ms"],
                result.media_sentences[1]["start_ms"],
            )

    def test_audio_pipeline_sentence_order_matches_audio_order(self):
        """Sentences must appear in the same order as in the audio timeline."""
        with tempfile.TemporaryDirectory() as tmpdir:
            media = Path(tmpdir) / "sample.mp3"
            media.write_bytes(b"fake-audio")
            mock_result = {
                "text": "First sentence. Second sentence. Third sentence.",
                "segments": [
                    {
                        "start": 0.0,
                        "end": 1.0,
                        "words": [
                            {"word": "First", "start": 0.0, "end": 0.2},
                            {"word": "sentence.", "start": 0.2, "end": 0.9},
                        ],
                    },
                    {
                        "start": 1.1,
                        "end": 2.2,
                        "words": [
                            {"word": "Second", "start": 1.1, "end": 1.5},
                            {"word": "sentence.", "start": 1.5, "end": 2.1},
                        ],
                    },
                    {
                        "start": 2.3,
                        "end": 3.4,
                        "words": [
                            {"word": "Third", "start": 2.3, "end": 2.7},
                            {"word": "sentence.", "start": 2.7, "end": 3.3},
                        ],
                    },
                ],
            }
            with (
                patch("ela_pipeline.runtime.media_pipeline._get_whisper_model_cached") as mock_model_factory,
                patch("whisper.load_audio", return_value=np.zeros(32_000, dtype=np.float32)),
                patch("ela_pipeline.runtime.media_pipeline._probe_media_duration_seconds", return_value=3.5),
            ):
                mock_model = mock_model_factory.return_value
                mock_model.transcribe.return_value = mock_result
                result = run_media_pipeline(source_path=str(media), sentence_contract_builder=self._builder)

            self.assertEqual(len(result.media_sentences), 3)
            starts = [s["start_ms"] for s in result.media_sentences]
            self.assertEqual(starts, sorted(starts), "Sentence start_ms must be in ascending order")
            self.assertEqual(result.media_sentences[0]["text_eng"], "First sentence.")
            self.assertEqual(result.media_sentences[1]["text_eng"], "Second sentence.")
            self.assertEqual(result.media_sentences[2]["text_eng"], "Third sentence.")


if __name__ == "__main__":
    unittest.main()
