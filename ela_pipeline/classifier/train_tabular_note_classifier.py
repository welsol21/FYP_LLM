"""Train a tabular note-id classifier on note-id dataset JSONL."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .train_tabular_cefr_baseline import train_tabular_cefr_baseline


def train_tabular_note_classifier(
    *,
    train_path: str,
    dev_path: str,
    test_path: str,
    output_dir: str,
    model_names: list[str] | None = None,
    seed: int = 42,
    feature_profile: str = "runtime_stable",
) -> dict[str, Any]:
    summary = train_tabular_cefr_baseline(
        train_path=train_path,
        dev_path=dev_path,
        test_path=test_path,
        output_dir=output_dir,
        model_names=model_names,
        seed=seed,
        label_field="note_id",
        feature_profile=feature_profile,
    )
    out_dir = Path(output_dir)
    base_model_path = out_dir / "best_tabular_cefr_baseline.joblib"
    note_model_path = out_dir / "best_tabular_note_classifier.joblib"
    if base_model_path.is_file():
        note_model_path.write_bytes(base_model_path.read_bytes())

    note_summary = {
        **summary,
        "task": "note_id_classification",
        "best_model_path": str(note_model_path),
    }
    (out_dir / "tabular_note_classifier_summary.json").write_text(
        json.dumps(note_summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return note_summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Train tabular note-id classifier.")
    parser.add_argument("--train-path", default="artifacts/classifier_note_id_v40/train.jsonl")
    parser.add_argument("--dev-path", default="artifacts/classifier_note_id_v40/dev.jsonl")
    parser.add_argument("--test-path", default="artifacts/classifier_note_id_v40/test.jsonl")
    parser.add_argument("--output-dir", default="artifacts/models/tabular_note_classifier_v40")
    parser.add_argument(
        "--model",
        action="append",
        default=[],
        choices=["xgboost_gpu"],
        help="Model name to run.",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--feature-profile", default="runtime_stable", choices=["full", "no_source", "runtime_stable"])
    args = parser.parse_args()
    summary = train_tabular_note_classifier(
        train_path=args.train_path,
        dev_path=args.dev_path,
        test_path=args.test_path,
        output_dir=args.output_dir,
        model_names=args.model or None,
        seed=args.seed,
        feature_profile=args.feature_profile,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
