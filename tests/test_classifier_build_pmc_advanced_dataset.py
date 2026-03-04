import io
import tarfile
import tempfile
import textwrap
import unittest
from pathlib import Path

from ela_pipeline.classifier.build_pmc_advanced_dataset import build_pmc_advanced_dataset


class BuildPMCOAAdvancedDatasetTests(unittest.TestCase):
    def test_build_pmc_advanced_dataset_creates_train_ready_rows(self):
        sample_xml = textwrap.dedent(
            """
            <article>
              <front>
                <journal-meta>
                  <journal-title-group>
                    <journal-title>Advanced Journal</journal-title>
                  </journal-title-group>
                </journal-meta>
                <article-meta>
                  <article-id pub-id-type="pmcid">PMC12345</article-id>
                  <title-group>
                    <article-title>Advanced timeline structures</article-title>
                  </title-group>
                  <permissions>
                    <license>
                      <license-p>CC BY</license-p>
                    </license>
                  </permissions>
                  <abstract>
                    <p>The samples had degraded before the second assay started.</p>
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
        ).strip().encode("utf-8")

        with tempfile.TemporaryDirectory() as tmp:
            tar_path = Path(tmp) / "pmc_sample.tar.gz"
            out_dir = Path(tmp) / "out"
            with tarfile.open(tar_path, "w:gz") as tf:
                info = tarfile.TarInfo("PMC012xxxxxx/PMC12345.xml")
                info.size = len(sample_xml)
                tf.addfile(info, io.BytesIO(sample_xml))

            summary = build_pmc_advanced_dataset(
                tar_path=str(tar_path),
                output_dir=str(out_dir),
                limit_articles=1,
                min_examples_per_class=1,
            )

            self.assertTrue(Path(summary["manifest_path"]).is_file())

        self.assertGreaterEqual(summary["mapped_rows_before_gates"], 1)
        self.assertIn("B2", summary["mapped_cefr_counts"])

    def test_build_pmc_advanced_dataset_can_prefilter_by_text_patterns(self):
        sample_xml = textwrap.dedent(
            """
            <article>
              <front>
                <article-meta>
                  <article-id pub-id-type="pmcid">PMC99999</article-id>
                  <title-group>
                    <article-title>Targeted modal perfects</article-title>
                  </title-group>
                  <abstract>
                    <p>The researchers should have verified the assay earlier. The control group was examined yesterday.</p>
                  </abstract>
                </article-meta>
              </front>
              <body>
                <sec>
                  <p>The subjects will have completed the protocol by the following week.</p>
                </sec>
              </body>
            </article>
            """
        ).strip().encode("utf-8")

        with tempfile.TemporaryDirectory() as tmp:
            tar_path = Path(tmp) / "pmc_targeted.tar.gz"
            out_dir = Path(tmp) / "out"
            with tarfile.open(tar_path, "w:gz") as tf:
                info = tarfile.TarInfo("PMC012xxxxxx/PMC99999.xml")
                info.size = len(sample_xml)
                tf.addfile(info, io.BytesIO(sample_xml))

            summary = build_pmc_advanced_dataset(
                tar_path=str(tar_path),
                output_dir=str(out_dir),
                limit_articles=1,
                text_patterns=[r"should have", r"will have"],
                min_examples_per_class=1,
            )

        self.assertGreaterEqual(summary["mapped_rows_before_gates"], 1)
        self.assertTrue(any(level in summary["mapped_cefr_counts"] for level in ("C1", "C2")))


if __name__ == "__main__":
    unittest.main()
