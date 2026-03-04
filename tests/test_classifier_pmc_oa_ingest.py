import tempfile
import textwrap
import unittest
from pathlib import Path

from ela_pipeline.classifier.pmc_oa_ingest import build_pmc_sentence_candidates, extract_pmc_article


class PMCOAIngestTests(unittest.TestCase):
    def test_extract_pmc_article_reads_core_fields(self):
        sample = textwrap.dedent(
            """
            <article>
              <front>
                <journal-meta>
                  <journal-title-group>
                    <journal-title>Journal of Advanced Grammar</journal-title>
                  </journal-title-group>
                </journal-meta>
                <article-meta>
                  <article-id pub-id-type="pmcid">PMC12345</article-id>
                  <title-group>
                    <article-title>Advanced clause interactions in scientific prose</article-title>
                  </title-group>
                  <permissions>
                    <license>
                      <license-p>This article is distributed under the terms of the Creative Commons Attribution License.</license-p>
                    </license>
                  </permissions>
                  <abstract>
                    <p>The experiment had been completed before the second phase began.</p>
                  </abstract>
                </article-meta>
              </front>
              <body>
                <sec>
                  <p>The samples will have degraded by the time the control group is evaluated.</p>
                </sec>
              </body>
            </article>
            """
        ).strip()

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "article.nxml"
            path.write_text(sample, encoding="utf-8")
            article = extract_pmc_article(str(path))

        self.assertEqual(article["article_id"], "PMC12345")
        self.assertEqual(article["journal_title"], "Journal of Advanced Grammar")
        self.assertIn("Advanced clause interactions", article["title"])
        self.assertEqual(len(article["abstract_paragraphs"]), 1)
        self.assertEqual(len(article["body_paragraphs"]), 1)
        self.assertIn("Creative Commons Attribution License", article["license_text"])

    def test_build_pmc_sentence_candidates_adds_provenance(self):
        article = {
            "article_id": "PMC12345",
            "journal_title": "Journal of Advanced Grammar",
            "license_text": "CC BY",
            "title": "Advanced clause interactions",
            "source_path": "/tmp/article.nxml",
            "abstract_paragraphs": ["The experiment had been completed before the second phase began. The first stage was delayed."],
            "body_paragraphs": ["The samples will have degraded by the time the control group is evaluated."],
        }

        rows = build_pmc_sentence_candidates(article)

        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["provenance"]["source"], "PMC_OA")
        self.assertEqual(rows[0]["provenance"]["article_id"], "PMC12345")
        self.assertEqual(rows[0]["provenance"]["sentence_index"], 1)
        self.assertEqual(rows[1]["provenance"]["sentence_index"], 2)
        self.assertEqual(rows[2]["provenance"]["section"], "body_paragraphs")


if __name__ == "__main__":
    unittest.main()
