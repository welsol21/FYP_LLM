import json
import tempfile
import textwrap
import unittest
from pathlib import Path

from ela_pipeline.classifier.build_ud_phase1_dataset import build_phase1_dataset_from_ud


class BuildUDPhase1DatasetTests(unittest.TestCase):
    def test_build_phase1_dataset_from_ud_writes_train_ready_rows(self):
        sample = textwrap.dedent(
            """
            # sent_id = ewt-train-1
            # text = She walks home.
            1\tShe\tshe\tPRON\tPRP\tCase=Nom|Number=Sing|Person=3\t2\tnsubj\t_\t_
            2\twalks\twalk\tVERB\tVBZ\tMood=Ind|Number=Sing|Person=3|Tense=Pres|VerbForm=Fin\t0\troot\t_\t_
            3\thome\thome\tADV\tRB\t_\t2\tadvmod\t_\tSpaceAfter=No
            4\t.\t.\tPUNCT\t.\t_\t2\tpunct\t_\t_

            # sent_id = ewt-train-2
            # text = She has finished the work.
            1\tShe\tshe\tPRON\tPRP\tCase=Nom|Number=Sing|Person=3\t3\tnsubj\t_\t_
            2\thas\thave\tAUX\tVBZ\tMood=Ind|Number=Sing|Person=3|Tense=Pres|VerbForm=Fin\t3\taux\t_\t_
            3\tfinished\tfinish\tVERB\tVBN\tTense=Past|VerbForm=Part\t0\troot\t_\t_
            4\tthe\tthe\tDET\tDT\tDefinite=Def|PronType=Art\t5\tdet\t_\t_
            5\twork\twork\tNOUN\tNN\tNumber=Sing\t3\tobj\t_\tSpaceAfter=No
            6\t.\t.\tPUNCT\t.\t_\t3\tpunct\t_\t_
            """
        ).strip()

        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "en_ewt-ud-train.conllu"
            src.write_text(sample + "\n", encoding="utf-8")

            out = build_phase1_dataset_from_ud(
                input_paths=[str(src)],
                output_dir=str(Path(tmp) / "out"),
                treebank="UD_English-EWT",
                split="train",
            )

            dataset_path = Path(out["dataset_path"])
            rows = [json.loads(line) for line in dataset_path.read_text(encoding="utf-8").splitlines() if line.strip()]

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["cefr_level"], "A1")
        self.assertIn("present_simple_affirmative", rows[0]["grammar_classes"])
        self.assertEqual(rows[1]["cefr_level"], "B1")
        self.assertIn("present_perfect_affirmative", rows[1]["grammar_classes"])
        self.assertTrue(rows[0]["note_blueprints"]["elementary_text"])
        self.assertEqual(rows[0]["provenance"]["treebank"], "UD_English-EWT")

    def test_build_phase1_dataset_from_ud_filters_ambiguous_rows_before_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "rows.conllu"
            src.write_text("", encoding="utf-8")
            out = build_phase1_dataset_from_ud(
                input_paths=[str(src)],
                output_dir=str(Path(tmp) / "out"),
                treebank="UD_English-EWT",
                split="train",
                prebuilt_rows=[
                    {
                        "text": "She walks home.",
                        "cefr_level": "A1",
                        "grammar_classes": ["present_simple_affirmative"],
                        "grammar_evidence": {"dep_signature": ["nsubj", "root"]},
                        "note_blueprints": {
                            "elementary_text": "A1 blueprint",
                            "intermediate_text": "A2 blueprint",
                            "advanced_text": "B1 blueprint",
                        },
                        "provenance": {"sent_id": "s1"},
                    },
                    {
                        "text": "They walk home.",
                        "cefr_level": "A2",
                        "grammar_classes": ["present_simple_affirmative"],
                        "grammar_evidence": {"dep_signature": ["nsubj", "root"]},
                        "note_blueprints": {
                            "elementary_text": "A1 blueprint",
                            "intermediate_text": "A2 blueprint",
                            "advanced_text": "B1 blueprint",
                        },
                        "provenance": {"sent_id": "s2"},
                    },
                ],
            )

            rows = [
                json.loads(line)
                for line in Path(out["dataset_path"]).read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        self.assertEqual(rows, [])
        self.assertFalse(out["gate_report"]["passed"])
        self.assertIn("grammar_combo_ambiguity", out["gate_report"]["failed_gates"])


if __name__ == "__main__":
    unittest.main()
