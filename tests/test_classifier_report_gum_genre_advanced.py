import tempfile
import textwrap
import unittest
from pathlib import Path

from ela_pipeline.classifier.report_gum_genre_advanced import build_gum_genre_advanced_report


class ReportGUMGenreAdvancedTests(unittest.TestCase):
    def test_build_gum_genre_advanced_report_counts_selected_genres_only(self):
        sample = textwrap.dedent(
            """
            # newdoc id = GUM_academic_demo
            # meta::genre = academic
            # sent_id = GUM_academic_demo-1
            # text = The study had shown results.
            1\tThe\tthe\tDET\tDT\t_\t2\tdet\t_\t_
            2\tstudy\tstudy\tNOUN\tNN\tNumber=Sing\t4\tnsubj\t_\t_
            3\thad\thave\tAUX\tVBD\tTense=Past|VerbForm=Fin\t4\taux\t_\t_
            4\tshown\tshow\tVERB\tVBN\tVerbForm=Part\t0\troot\t_\t_
            5\tresults\tresult\tNOUN\tNNS\tNumber=Plur\t4\tobj\t_\tSpaceAfter=No
            6\t.\t.\tPUNCT\t.\t_\t4\tpunct\t_\t_

            # newdoc id = GUM_conversation_demo
            # meta::genre = conversation
            # sent_id = GUM_conversation_demo-1
            # text = We talked yesterday.
            1\tWe\twe\tPRON\tPRP\tCase=Nom\t2\tnsubj\t_\t_
            2\ttalked\ttalk\tVERB\tVBD\tTense=Past|VerbForm=Fin\t0\troot\t_\t_
            3\tyesterday\tyesterday\tADV\tRB\t_\t2\tadvmod\t_\tSpaceAfter=No
            4\t.\t.\tPUNCT\t.\t_\t2\tpunct\t_\t_
            """
        ).strip()

        with tempfile.TemporaryDirectory() as tmp:
            treebank_dir = Path(tmp) / "UD_English-GUM"
            treebank_dir.mkdir(parents=True, exist_ok=True)
            for split in ("train", "dev", "test"):
                (treebank_dir / f"en_gum-ud-{split}.conllu").write_text(sample + "\n", encoding="utf-8")

            report = build_gum_genre_advanced_report(
                treebank_dir=str(treebank_dir),
                genres=["academic"],
            )

        self.assertEqual(report["selected_genres"], ["academic"])
        self.assertEqual(len(report["genres"]), 1)
        self.assertEqual(report["genres"][0]["genre"], "academic")
        self.assertEqual(report["genres"][0]["advanced_sentences"], 3)
        support = {(row["cefr_level"], row["class_id"]): row["count"] for row in report["aggregate_class_support"]}
        self.assertEqual(support[("B2", "past_perfect")], 3)


if __name__ == "__main__":
    unittest.main()
