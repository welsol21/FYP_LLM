import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from ela_pipeline.classifier.build_masc_advanced_dataset import build_masc_advanced_dataset


def _make_sentence(lines: list[str]) -> str:
    return "\n".join(lines) + "\n\n"


class BuildMascAdvancedDatasetTests(unittest.TestCase):
    def test_build_masc_advanced_dataset_creates_train_ready_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "masc-conll.zip"
            output_dir = Path(tmp) / "out"
            content = (
                _make_sentence(
                    [
                        "1\tShe\tshe\tPRP\t_\tShe\tshe\tPRP\t4\tSBJ\t_\t_",
                        "2\twill\twill\tMD\t_\twill\twill\tMD\t4\tDEP\t_\t_",
                        "3\thave\thave\tVB\t_\thave\thave\tVB\t4\tVC\t_\t_",
                        "4\tfinished\tfinish\tVBN\t_\tfinished\tfinish\tVBN\t0\tROOT\t_\t_",
                        "5\t.\t.\t.\t_\t.\t.\t.\t4\tP\t_\t_",
                    ]
                )
                + _make_sentence(
                    [
                        "1\tHe\the\tPRP\t_\tHe\the\tPRP\t4\tSBJ\t_\t_",
                        "2\tshould\tshould\tMD\t_\tshould\tshould\tMD\t4\tDEP\t_\t_",
                        "3\thave\thave\tVB\t_\thave\thave\tVB\t4\tVC\t_\t_",
                        "4\tleft\tleave\tVBN\t_\tleft\tleave\tVBN\t0\tROOT\t_\t_",
                        "5\t.\t.\t.\t_\t.\t.\t.\t4\tP\t_\t_",
                    ]
                )
            )
            with ZipFile(zip_path, "w") as zf:
                zf.writestr("masc-conll/data/written/sample.conll", content)

            summary = build_masc_advanced_dataset(
                zip_path=str(zip_path),
                output_dir=str(output_dir),
                min_chars=5,
                min_examples_per_class=1,
            )

            self.assertEqual(summary["accepted_rows"], 2)
            self.assertTrue(Path(summary["dataset_path"]).is_file())
            self.assertTrue(summary["gate_report"]["passed"])
