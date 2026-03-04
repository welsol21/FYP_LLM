import json
import tempfile
import unittest
from pathlib import Path

from ela_pipeline.classifier.build_full_ladder_classifier_dataset import (
    _extract_dataset_path_from_report,
    _fails_curriculum_hygiene,
    build_full_ladder_classifier_dataset,
)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


class BuildFullLadderClassifierDatasetTests(unittest.TestCase):
    def test_curriculum_hygiene_rejects_a1_rows_with_complex_clause_load(self):
        row = {
            "cefr_label": "A1",
            "grammar_evidence": {
                "token_count": 26,
                "dep_signature": ["aux", "nsubj", "advcl", "root", "ccomp"],
            },
        }
        self.assertTrue(_fails_curriculum_hygiene(row))

    def test_curriculum_hygiene_keeps_short_a1_rows(self):
        row = {
            "cefr_label": "A1",
            "grammar_evidence": {
                "token_count": 6,
                "dep_signature": ["nsubj", "root", "obj"],
            },
        }
        self.assertFalse(_fails_curriculum_hygiene(row))

    def test_extract_dataset_path_from_report_handles_flat_and_nested_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nested = root / "nested.json"
            flat = root / "flat.json"
            nested.write_text(json.dumps({"summary": {"dataset_path": "a.jsonl"}}), encoding="utf-8")
            flat.write_text(json.dumps({"dataset_path": "b.jsonl"}), encoding="utf-8")

            self.assertEqual(_extract_dataset_path_from_report(str(nested)), "a.jsonl")
            self.assertEqual(_extract_dataset_path_from_report(str(flat)), "b.jsonl")

    def test_build_full_ladder_dataset_drops_ud_collisions_and_cross_level_conflicts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out_dir = root / "out"

            ud_train = root / "ud_train.jsonl"
            ud_dev = root / "ud_dev.jsonl"
            ud_test = root / "ud_test.jsonl"
            adv = root / "adv.jsonl"
            adv_report = root / "adv_report.json"
            ud_summary = root / "ud_summary.json"

            _write_jsonl(
                ud_train,
                [
                    {"input": "task text: alpha", "cefr_label": "A1", "source_text": "Alpha.", "grammar_classes": ["present_simple_affirmative"]},
                ],
            )
            _write_jsonl(ud_dev, [{"input": "task text: beta", "cefr_label": "A2", "source_text": "Beta."}])
            _write_jsonl(ud_test, [{"input": "task text: gamma", "cefr_label": "B1", "source_text": "Gamma."}])
            _write_jsonl(
                adv,
                [
                    {"input": "task text: alpha-dup", "cefr_label": "C1", "source_text": "Alpha."},
                    {"input": "task text: delta-a", "cefr_label": "C1", "source_text": "Delta."},
                    {"input": "task text: delta-b", "cefr_label": "C2", "source_text": "Delta."},
                    {"input": "task text: epsilon", "cefr_label": "C2", "source_text": "Epsilon."},
                ],
            )
            adv_report.write_text(json.dumps({"dataset_path": str(adv)}), encoding="utf-8")
            ud_summary.write_text(
                json.dumps(
                    {
                        "splits": {
                            "train": {"dataset_path": str(ud_train)},
                            "dev": {"dataset_path": str(ud_dev)},
                            "test": {"dataset_path": str(ud_test)},
                        }
                    }
                ),
                encoding="utf-8",
            )

            summary = build_full_ladder_classifier_dataset(
                ud_summary_paths=[str(ud_summary)],
                advanced_report_paths=[str(adv_report)],
                output_dir=str(out_dir),
                seed=7,
                advanced_dev_ratio=0.0,
                advanced_test_ratio=0.0,
            )

            self.assertEqual(summary["advanced_conflict_rejections"], 2)
            self.assertEqual(summary["advanced_ud_collision_rejections"], 1)
            self.assertEqual(summary["advanced_rows_added"]["train"], 1)

            train_rows = [json.loads(line) for line in (out_dir / "train_classifier.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual({row["source_text"] for row in train_rows}, {"Alpha.", "Epsilon."})

            rejected_conflicts = [json.loads(line) for line in (out_dir / "rejected_advanced_conflicts.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual({row["source_text"] for row in rejected_conflicts}, {"Delta."})

    def test_build_full_ladder_dataset_stratifies_advanced_rows_into_dev_and_test(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out_dir = root / "out"

            ud_train = root / "ud_train.jsonl"
            ud_dev = root / "ud_dev.jsonl"
            ud_test = root / "ud_test.jsonl"
            adv = root / "adv.jsonl"
            adv_report = root / "adv_report.json"
            ud_summary = root / "ud_summary.json"

            _write_jsonl(ud_train, [])
            _write_jsonl(ud_dev, [])
            _write_jsonl(ud_test, [])

            rows = []
            for idx in range(10):
                rows.append({"input": f"text c1 {idx}", "cefr_label": "C1", "source_text": f"C1 sample {idx}."})
                rows.append({"input": f"text c2 {idx}", "cefr_label": "C2", "source_text": f"C2 sample {idx}."})
            _write_jsonl(adv, rows)
            adv_report.write_text(json.dumps({"summary": {"dataset_path": str(adv)}}), encoding="utf-8")
            ud_summary.write_text(
                json.dumps(
                    {
                        "splits": {
                            "train": {"dataset_path": str(ud_train)},
                            "dev": {"dataset_path": str(ud_dev)},
                            "test": {"dataset_path": str(ud_test)},
                        }
                    }
                ),
                encoding="utf-8",
            )

            summary = build_full_ladder_classifier_dataset(
                ud_summary_paths=[str(ud_summary)],
                advanced_report_paths=[str(adv_report)],
                output_dir=str(out_dir),
                seed=13,
                advanced_dev_ratio=0.2,
                advanced_test_ratio=0.2,
            )

            self.assertEqual(summary["advanced_rows_added"]["train"], 12)
            self.assertEqual(summary["advanced_rows_added"]["dev"], 4)
            self.assertEqual(summary["advanced_rows_added"]["test"], 4)

            dev_rows = [json.loads(line) for line in (out_dir / "dev_classifier.jsonl").read_text(encoding="utf-8").splitlines()]
            test_rows = [json.loads(line) for line in (out_dir / "test_classifier.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(sorted(row["cefr_label"] for row in dev_rows), ["C1", "C1", "C2", "C2"])
            self.assertEqual(sorted(row["cefr_label"] for row in test_rows), ["C1", "C1", "C2", "C2"])

    def test_build_full_ladder_dataset_preserves_required_train_support_thresholds(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out_dir = root / "out"
            ud_train = root / "ud_train.jsonl"
            ud_dev = root / "ud_dev.jsonl"
            ud_test = root / "ud_test.jsonl"
            adv = root / "adv.jsonl"
            adv_report = root / "adv_report.json"
            ud_summary = root / "ud_summary.json"
            thresholds = root / "advanced_thresholds.json"

            _write_jsonl(ud_train, [])
            _write_jsonl(ud_dev, [])
            _write_jsonl(ud_test, [])
            _write_jsonl(
                adv,
                [
                    {
                        "input": f"text c2 {idx}",
                        "cefr_label": "C2",
                        "source_text": f"C2 sample {idx}.",
                        "grammar_classes": ["future_perfect"],
                    }
                    for idx in range(52)
                ],
            )
            adv_report.write_text(json.dumps({"summary": {"dataset_path": str(adv)}}), encoding="utf-8")
            ud_summary.write_text(
                json.dumps(
                    {
                        "splits": {
                            "train": {"dataset_path": str(ud_train)},
                            "dev": {"dataset_path": str(ud_dev)},
                            "test": {"dataset_path": str(ud_test)},
                        }
                    }
                ),
                encoding="utf-8",
            )
            thresholds.write_text(
                json.dumps(
                    {
                        "advanced_thresholds": [
                            {
                                "cefr_level": "C2",
                                "class_id": "future_perfect",
                                "required_train_support": 50,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            summary = build_full_ladder_classifier_dataset(
                ud_summary_paths=[str(ud_summary)],
                advanced_report_paths=[str(adv_report)],
                output_dir=str(out_dir),
                seed=13,
                advanced_dev_ratio=0.1,
                advanced_test_ratio=0.1,
                advanced_threshold_report_path=str(thresholds),
            )

            self.assertEqual(summary["advanced_rows_added"]["train"], 50)
            self.assertEqual(summary["advanced_rows_added"]["dev"], 1)
            self.assertEqual(summary["advanced_rows_added"]["test"], 1)


if __name__ == "__main__":
    unittest.main()
