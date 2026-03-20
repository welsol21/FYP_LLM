import tempfile
import unittest
from pathlib import Path

from ela_pipeline.dataset.build_oxford_targeted_note_context_pairs import build_oxford_targeted_note_context_pairs


class OxfordTargetedNoteContextPairTests(unittest.TestCase):
    def test_build_oxford_targeted_note_context_pairs_extracts_targeted_examples(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload_path = Path(tmp) / "payload.txt"
            payload_path.write_text(
                "\n".join(
                    [
                        "passive (adj.) Of a clause designating passive voice.",
                        "The *agent is mentioned in the *by-phrase, e.g.",
                        "The window was shattered by my neighbour’s son",
                        "Rome was not built in a day",
                        "passive auxiliary be See passive.",
                        "tag (n.)",
                        "In the most usual cases, a negative tag is added to a positive statement, e.g.",
                        "It’s been cold this week, hasn’t it?",
                        "tautology The saying of the same thing over again in different words.",
                    ]
                ),
                encoding="utf-8",
            )

            rows, report = build_oxford_targeted_note_context_pairs(
                payload_txt=str(payload_path),
                source_path="/tmp/book.pdf",
            )

        self.assertGreaterEqual(report["pairs_total"], 2)
        self.assertTrue(any(row["entry_head"] == "passive" for row in rows))
        self.assertTrue(any(row["entry_head"] == "question tag" for row in rows))


if __name__ == "__main__":
    unittest.main()
