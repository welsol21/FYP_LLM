import tempfile
import textwrap
import unittest
from pathlib import Path

from ela_pipeline.classifier.gutenberg_catalog import (
    build_gutenberg_text_url,
    filter_gutenberg_catalog,
    load_gutenberg_catalog,
)


class GutenbergCatalogTests(unittest.TestCase):
    def test_build_gutenberg_text_url_uses_epub_cache_pattern(self):
        self.assertEqual(
            build_gutenberg_text_url("1342"),
            "https://www.gutenberg.org/cache/epub/1342/pg1342.txt",
        )

    def test_load_gutenberg_catalog_reads_csv_rows(self):
        sample = textwrap.dedent(
            """\
            ID,Title,Authors,Language,Subjects,Bookshelves,Text#
            1,Essays of Language,Jane Doe,en,Essays; Language and languages,Essay Collection,https://example.org/1.txt
            2,Modern Fiction,John Doe,en,Fiction; Psychological fiction,Best Fiction,https://example.org/2.txt
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pg_catalog.csv"
            path.write_text(sample, encoding="utf-8")
            rows = load_gutenberg_catalog(str(path))

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["Title"], "Essays of Language")

    def test_filter_gutenberg_catalog_selects_english_essays_and_fiction(self):
        rows = [
            {
                "ID": "1",
                "Title": "Essays of Language",
                "Authors": "Jane Doe",
                "Language": "en",
                "Subjects": "Essays; Language and languages",
                "Bookshelves": "Essay Collection",
                "LoCC": "PN",
                "Text#": "1",
            },
            {
                "ID": "2",
                "Title": "Modern Fiction",
                "Authors": "John Doe",
                "Language": "en",
                "Subjects": "Fiction; Psychological fiction",
                "Bookshelves": "Best Fiction",
                "LoCC": "PR",
                "Text#": "2",
            },
            {
                "ID": "3",
                "Title": "German Essays",
                "Authors": "Max Mustermann",
                "Language": "de",
                "Subjects": "Essays",
                "Bookshelves": "Essay Collection",
                "LoCC": "PN",
                "Text#": "3",
            },
            {
                "ID": "4",
                "Title": "American Speech",
                "Authors": "Jane Roe",
                "Language": "en",
                "Subjects": "Speeches",
                "Bookshelves": "Category: Essays, Letters & Speeches; Politics",
                "LoCC": "E",
                "Text#": "4",
            },
            {
                "ID": "5",
                "Title": "Juvenile Fantasy",
                "Authors": "J. Doe",
                "Language": "en",
                "Subjects": "Fantasy fiction; Juvenile fiction",
                "Bookshelves": "Children's Literature; Category: Novels",
                "LoCC": "PR; PZ",
                "Text#": "5",
            },
        ]

        selected = filter_gutenberg_catalog(
            rows,
            subject_keywords=["Essays", "Fiction"],
            type_keywords=["Essay", "Fiction"],
            language="en",
            allowed_locc_prefixes=["P", "PN", "PR", "PS"],
            exclude_bookshelf_keywords=["Politics", "History", "Law", "Speeches", "Children", "Juvenile", "Young Adult"],
        )

        self.assertEqual(len(selected), 2)
        self.assertEqual(selected[0]["title"], "Essays of Language")
        self.assertEqual(selected[1]["title"], "Modern Fiction")
        self.assertEqual(selected[0]["text_url"], "https://www.gutenberg.org/cache/epub/1/pg1.txt")


if __name__ == "__main__":
    unittest.main()
