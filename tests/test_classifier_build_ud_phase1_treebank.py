import json
import tempfile
import textwrap
import unittest
from pathlib import Path

from ela_pipeline.classifier.build_ud_phase1_dataset import build_phase1_treebank_dataset


class BuildUDPhase1TreebankTests(unittest.TestCase):
    def test_build_phase1_treebank_dataset_builds_multiple_splits_and_summary(self):
        train_sample = textwrap.dedent(
            """
            # sent_id = ewt-train-1
            # text = She walks home.
            1\tShe\tshe\tPRON\tPRP\tCase=Nom|Number=Sing|Person=3\t2\tnsubj\t_\t_
            2\twalks\twalk\tVERB\tVBZ\tMood=Ind|Number=Sing|Person=3|Tense=Pres|VerbForm=Fin\t0\troot\t_\t_
            3\thome\thome\tADV\tRB\t_\t2\tadvmod\t_\tSpaceAfter=No
            4\t.\t.\tPUNCT\t.\t_\t2\tpunct\t_\t_
            """
        ).strip()
        dev_sample = textwrap.dedent(
            """
            # sent_id = ewt-dev-1
            # text = She walked home.
            1\tShe\tshe\tPRON\tPRP\tCase=Nom|Number=Sing|Person=3\t2\tnsubj\t_\t_
            2\twalked\twalk\tVERB\tVBD\tTense=Past|VerbForm=Fin\t0\troot\t_\t_
            3\thome\thome\tADV\tRB\t_\t2\tadvmod\t_\tSpaceAfter=No
            4\t.\t.\tPUNCT\t.\t_\t2\tpunct\t_\t_
            """
        ).strip()
        test_sample = textwrap.dedent(
            """
            # sent_id = ewt-test-1
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
            root = Path(tmp) / "UD_English-EWT"
            root.mkdir(parents=True, exist_ok=True)
            (root / "en_ewt-ud-train.conllu").write_text(train_sample + "\n", encoding="utf-8")
            (root / "en_ewt-ud-dev.conllu").write_text(dev_sample + "\n", encoding="utf-8")
            (root / "en_ewt-ud-test.conllu").write_text(test_sample + "\n", encoding="utf-8")

            summary = build_phase1_treebank_dataset(
                treebank_dir=str(root),
                output_dir=str(Path(tmp) / "out"),
                treebank_name="UD_English-EWT",
            )

            self.assertEqual(summary["treebank"], "UD_English-EWT")
            self.assertEqual(summary["splits"]["train"]["accepted_rows"], 1)
            self.assertEqual(summary["splits"]["dev"]["accepted_rows"], 1)
            self.assertEqual(summary["splits"]["test"]["accepted_rows"], 1)

            summary_path = Path(summary["summary_path"])
            payload = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertIn("splits", payload)
            self.assertEqual(payload["splits"]["test"]["gate_report"]["passed"], True)


if __name__ == "__main__":
    unittest.main()
