import json
import tempfile
import unittest
from pathlib import Path

from ela_pipeline.classifier.report_advanced_coverage import build_advanced_coverage_report


class ReportAdvancedCoverageTests(unittest.TestCase):
    def test_build_advanced_coverage_report_combines_train_and_control_support(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            ud_train = base / "train.jsonl"
            ud_dev = base / "dev.jsonl"
            ud_test = base / "test.jsonl"
            oanc_probe = base / "oanc_probe.json"
            oanc_targeted = base / "oanc_targeted.json"
            masc_probe = base / "masc_probe.json"
            pmc_probe = base / "pmc_probe.json"
            gutenberg_probe = base / "gutenberg_probe.json"

            ud_train.write_text(
                "\n".join(
                    json.dumps(row)
                    for row in [
                        {"cefr_level": "B2", "grammar_classes": ["passive_voice"]},
                        {"cefr_level": "B2", "grammar_classes": ["past_perfect"]},
                    ]
                ),
                encoding="utf-8",
            )
            ud_dev.write_text(json.dumps({"cefr_level": "B2", "grammar_classes": ["passive_voice"]}) + "\n", encoding="utf-8")
            ud_test.write_text(json.dumps({"cefr_level": "C1", "grammar_classes": ["modal_perfect"]}) + "\n", encoding="utf-8")
            oanc_probe.write_text(
                json.dumps(
                    {
                        "summary": {
                            "mapped_rows_before_gates": 2,
                            "mapped_cefr_counts": {"C2": 1},
                            "mapped_class_support": [{"cefr_level": "C2", "class_id": "future_perfect", "count": 1}],
                        }
                    }
                ),
                encoding="utf-8",
            )
            oanc_targeted.write_text(
                json.dumps(
                    {
                        "summary": {
                            "mapped_rows_before_gates": 1,
                            "mapped_cefr_counts": {"C1": 1},
                            "mapped_class_support": [{"cefr_level": "C1", "class_id": "modal_perfect", "count": 1}],
                        }
                    }
                ),
                encoding="utf-8",
            )
            masc_probe.write_text(
                json.dumps(
                    {
                        "summary": {
                            "mapped_rows_before_gates": 1,
                            "mapped_cefr_counts": {"C1": 1},
                            "mapped_class_support": [{"cefr_level": "C1", "class_id": "modal_perfect", "count": 1}],
                        }
                    }
                ),
                encoding="utf-8",
            )
            pmc_probe.write_text(
                json.dumps(
                    {
                        "summary": {
                            "mapped_rows_before_gates": 2,
                            "mapped_cefr_counts": {"C1": 1, "C2": 1},
                            "mapped_class_support": [
                                {"cefr_level": "C1", "class_id": "modal_perfect", "count": 1},
                                {"cefr_level": "C2", "class_id": "future_perfect", "count": 1},
                            ],
                        }
                    }
                ),
                encoding="utf-8",
            )
            gutenberg_probe.write_text(
                json.dumps(
                    {
                        "summary": {
                            "mapped_rows_before_gates": 4,
                            "mapped_cefr_counts": {"C1": 3, "C2": 1},
                            "mapped_class_support": [
                                {"cefr_level": "C1", "class_id": "modal_perfect", "count": 3},
                                {"cefr_level": "C2", "class_id": "future_perfect", "count": 1},
                            ],
                        }
                    }
                ),
                encoding="utf-8",
            )

            report = build_advanced_coverage_report(
                ud_train_path=str(ud_train),
                ud_dev_path=str(ud_dev),
                ud_test_path=str(ud_test),
                oanc_probe_report_path=str(oanc_probe),
                oanc_targeted_report_path=str(oanc_targeted),
                masc_probe_report_path=str(masc_probe),
                pmc_probe_report_path=str(pmc_probe),
                gutenberg_probe_report_path=str(gutenberg_probe),
            )

        self.assertFalse(report["overall_advanced_readiness"])
        thresholds = {(row["cefr_level"], row["class_id"]): row for row in report["advanced_thresholds"]}
        self.assertEqual(thresholds[("C1", "modal_perfect")]["observed_train_support"], 5)
        self.assertEqual(thresholds[("C1", "modal_perfect")]["observed_control_support"], 2)
        self.assertEqual(report["sources"]["pmc_mapped_total"], 2)
        self.assertEqual(report["sources"]["gutenberg_mapped_total"], 4)
