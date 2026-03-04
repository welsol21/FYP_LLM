import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from ela_pipeline.classifier.masc_ingest import load_masc_conll_sentences


def _make_sentence(lines: list[str]) -> str:
    return "\n".join(lines) + "\n\n"


class MascIngestTests(unittest.TestCase):
    def test_load_masc_conll_sentences_reads_zip_and_attaches_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "masc-conll.zip"
            content = _make_sentence(
                [
                    "1\tThey\tthey\tPRP\t_\tThey\tthey\tPRP\t4\tSBJ\t_\t_",
                    "2\twill\twill\tMD\t_\twill\twill\tMD\t4\tDEP\t_\t_",
                    "3\thave\thave\tVB\t_\thave\thave\tVB\t4\tVC\t_\t_",
                    "4\tfinished\tfinish\tVBN\t_\tfinished\tfinish\tVBN\t0\tROOT\t_\t_",
                    "5\t.\t.\t.\t_\t.\t.\t.\t4\tP\t_\t_",
                ]
            )
            with ZipFile(zip_path, "w") as zf:
                zf.writestr("masc-conll/data/written/sample.conll", content)

            rows = load_masc_conll_sentences(str(zip_path), min_chars=5)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["text"], "They will have finished.")
        self.assertEqual(rows[0]["provenance"]["source"], "MASC")
        self.assertEqual(rows[0]["provenance"]["genre_bucket"], "written")

    def test_load_masc_conll_sentences_uses_split_form_for_padded_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "masc-conll.zip"
            content = _make_sentence(
                [
                    "1\tfollow-up\tfollow-up\tNN\t_\tfollow\tfollow\tNN\t2\tNMOD\t_\t_",
                    "2\t_\t_\t_\t_\t-\t-\tHYPH\t1\tHYPH\t_\t_",
                    "3\t_\t_\t_\t_\tup\tup\tNN\t1\tDEP\t_\t_",
                    "4\tmatters\tmatter\tVBZ\t_\tmatters\tmatter\tVBZ\t0\tROOT\t_\t_",
                    "5\t.\t.\t.\t_\t.\t.\t.\t4\tP\t_\t_",
                ]
            )
            with ZipFile(zip_path, "w") as zf:
                zf.writestr("masc-conll/data/written/sample.conll", content)

            rows = load_masc_conll_sentences(str(zip_path), min_chars=5)

        self.assertEqual(rows[0]["text"], "follow-up matters.")
