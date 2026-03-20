import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from ela_pipeline.dataset.book_extraction import UniversalBookExtractionEngine, build_default_parsers
from ela_pipeline.dataset.book_extraction.engine import BookTextPayload
from ela_pipeline.dataset.book_extraction.parsers import (
    DjvuBookParser,
    DocBookParser,
    DocxBookParser,
    EpubBookParser,
    OcrImageBookParser,
    PdfBookParser,
    ZipBookParser,
)


class BookExtractionEngineTests(unittest.TestCase):
    def test_engine_caches_parsed_book_text_to_disk(self):
        class FakeParser:
            name = "fake"

            def __init__(self):
                self.calls = 0

            def supports(self, path: str) -> bool:
                return str(path).endswith(".fake")

            def parse(self, path: str) -> BookTextPayload:
                self.calls += 1
                return BookTextPayload(
                    source_path=path,
                    parser_name="fake",
                    format="fake",
                    text="Question tags ask for confirmation.",
                )

        parser = FakeParser()
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "sample.fake"
            source.write_text("dummy", encoding="utf-8")
            cache_dir = Path(tmp) / "cache"
            engine = UniversalBookExtractionEngine(parsers=[parser], cache_dir=str(cache_dir))
            first = engine.parse_book(str(source))
            second = engine.parse_book(str(source))
            self.assertEqual(parser.calls, 1)
            self.assertEqual(first.text, second.text)
            self.assertEqual(first.metadata.get("cache_status"), "miss")
            self.assertEqual(second.metadata.get("cache_status"), "hit")
            payload_files = list(cache_dir.rglob("payload.txt"))
            meta_files = list(cache_dir.rglob("payload.json"))
            self.assertEqual(len(payload_files), 1)
            self.assertEqual(len(meta_files), 1)

    def test_engine_extracts_snippet_from_heading_anchor(self):
        engine = UniversalBookExtractionEngine(parsers=[])
        payload = BookTextPayload(
            source_path="/tmp/fake.pdf",
            parser_name="fake",
            format="pdf",
            text=(
                "Intro\n\n"
                "Relative Clauses\n"
                "Relative clauses add information about a noun in the sentence.\n"
                "They are often introduced by relative pronouns.\n\n"
                "Quiz\n"
            ),
        )
        snippets = engine.extract_from_payload(payload)
        self.assertEqual(len(snippets), 1)
        self.assertEqual(snippets[0].topic_key, "relative_clauses")
        self.assertIn("add information about a noun", snippets[0].snippet_text)

    def test_epub_parser_reads_html_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.epub"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("OEBPS/chapter1.xhtml", "<html><body><h1>Question tags</h1><p>Question tags ask for confirmation.</p></body></html>")
            payload = EpubBookParser().parse(str(path))
            self.assertEqual(payload.format, "epub")
            self.assertIn("Question tags ask for confirmation.", payload.text)
            engine = UniversalBookExtractionEngine(parsers=[])
            snippets = engine.extract_from_payload(payload)
            self.assertEqual(len(snippets), 1)
            self.assertEqual(snippets[0].topic_key, "question_tags")

    @patch("ela_pipeline.dataset.book_extraction.parsers._run_text_command", return_value="Passive Voice\nA passive clause foregrounds the affected participant.\n")
    def test_pdf_parser_uses_pdftotext_adapter(self, _mock_run):
        payload = PdfBookParser().parse("/tmp/book.pdf")
        self.assertEqual(payload.format, "pdf")
        self.assertIn("Passive Voice", payload.text)

    @patch(
        "ela_pipeline.dataset.book_extraction.parsers._ocr_pdf_to_text",
        return_value=(
            "Question Tags\n"
            "Question tags ask for confirmation after a statement and often repeat the auxiliary verb.\n"
            "They are common in spoken English and help the speaker check agreement.\n",
            {"ocr_used": True},
        ),
    )
    @patch("ela_pipeline.dataset.book_extraction.parsers._run_text_command", return_value="")
    def test_pdf_parser_falls_back_to_ocr_for_scanned_pdf(self, _mock_run, _mock_ocr):
        payload = PdfBookParser().parse("/tmp/scan.pdf")
        self.assertEqual(payload.format, "pdf")
        self.assertTrue(payload.metadata.get("ocr_used"))
        self.assertIn("Question tags ask for confirmation", payload.text)

    @patch("ela_pipeline.dataset.book_extraction.parsers._run_text_command", return_value="Relative Clauses\nA relative clause modifies a noun.\n")
    def test_djvu_parser_uses_djvutxt_adapter(self, _mock_run):
        payload = DjvuBookParser().parse("/tmp/book.djvu")
        self.assertEqual(payload.format, "djvu")
        self.assertIn("Relative Clauses", payload.text)

    @patch("ela_pipeline.dataset.book_extraction.parsers._ocr_image_to_text", return_value="Prepositions\nA preposition links a noun phrase to another element.\n")
    def test_image_parser_uses_tesseract_adapter(self, _mock_ocr):
        payload = OcrImageBookParser().parse("/tmp/book.png")
        self.assertEqual(payload.format, "image")
        self.assertTrue(payload.metadata.get("ocr_used"))
        self.assertIn("Prepositions", payload.text)

    def test_docx_parser_reads_word_xml(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.docx"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr(
                    "word/document.xml",
                    (
                        '<?xml version="1.0" encoding="UTF-8"?>'
                        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                        "<w:body><w:p><w:r><w:t>Question tags</w:t></w:r></w:p>"
                        "<w:p><w:r><w:t>Question tags ask for confirmation.</w:t></w:r></w:p></w:body>"
                        "</w:document>"
                    ),
                )
            payload = DocxBookParser().parse(str(path))
            self.assertEqual(payload.format, "docx")
            self.assertIn("Question tags ask for confirmation.", payload.text)

    @patch("ela_pipeline.dataset.book_extraction.parsers.subprocess.run")
    def test_doc_parser_uses_soffice_conversion(self, mock_run):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "sample.doc"
            source.write_bytes(b"fake")
            converted = Path(tmp) / "sample.txt"
            converted.write_text("Relative clauses add information about a noun.\n", encoding="utf-8")
            mock_run.return_value.returncode = 0
            mock_run.return_value.stderr = ""
            mock_run.return_value.stdout = ""
            with patch("tempfile.TemporaryDirectory") as mocked_tmp:
                mocked_tmp.return_value.__enter__.return_value = tmp
                mocked_tmp.return_value.__exit__.return_value = False
                payload = DocBookParser().parse(str(source))
        self.assertEqual(payload.format, "doc")
        self.assertIn("Relative clauses add information", payload.text)

    def test_zip_parser_aggregates_supported_members(self):
        class FakePdfParser:
            name = "pdf"

            def supports(self, path: str) -> bool:
                return str(path).endswith(".pdf")

            def parse(self, path: str) -> BookTextPayload:
                return BookTextPayload(
                    source_path=path,
                    parser_name="pdf",
                    format="pdf",
                    text="Passive voice focuses on the receiver of the action.\n",
                )

        pdf_parser = FakePdfParser()
        zip_parser = ZipBookParser(child_parsers=[pdf_parser])
        with tempfile.TemporaryDirectory() as tmp:
            archive_path = Path(tmp) / "books.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("inside/book.pdf", b"%PDF-FAKE")
                archive.writestr("inside/ignore.bin", b"\x00\x01")
            payload = zip_parser.parse(str(archive_path))
        self.assertEqual(payload.format, "zip")
        self.assertIn("inside/book.pdf", payload.text)
        self.assertEqual(payload.metadata["parsed_members"], ["inside/book.pdf"])

    def test_default_parsers_cover_pdf_epub_and_djvu(self):
        engine = UniversalBookExtractionEngine(parsers=build_default_parsers())
        self.assertEqual(engine.resolve_parser("/tmp/a.pdf").name, "pdf")
        self.assertEqual(engine.resolve_parser("/tmp/a.epub").name, "epub")
        self.assertEqual(engine.resolve_parser("/tmp/a.djvu").name, "djvu")
        self.assertEqual(engine.resolve_parser("/tmp/a.zip").name, "zip")
        self.assertEqual(engine.resolve_parser("/tmp/a.doc").name, "doc")
        self.assertEqual(engine.resolve_parser("/tmp/a.docx").name, "docx")
        self.assertEqual(engine.resolve_parser("/tmp/a.png").name, "ocr_image")


if __name__ == "__main__":
    unittest.main()
