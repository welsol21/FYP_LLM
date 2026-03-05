"""Train a single RandomForest that predicts CEFR + grammar class jointly."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from typing import Any

import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction import DictVectorizer
from sklearn.metrics import accuracy_score, f1_score
from sklearn.pipeline import Pipeline

from .metadata import build_classifier_metadata_from_dataset
from .train_tabular_cefr_baseline import extract_tabular_features, project_feature_profile


CEFR_ORDER = ("A1", "A2", "B1", "B2", "C1", "C2")


def _load_jsonl(path: str) -> list[dict[str, Any]]:
    src = Path(path)
    if not src.is_file():
        raise FileNotFoundError(f"dataset file not found: {path}")
    out: list[dict[str, Any]] = []
    with src.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                out.append(json.loads(line))
    return out


def _safe_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip().lower() for item in value if str(item).strip()]


def _primary_class(row: dict[str, Any]) -> str:
    classes = _safe_list(row.get("grammar_classes"))
    return classes[0] if classes else "unknown_class"


def _normalize_cefr(value: Any) -> str:
    level = str(value or "").strip().upper()
    return level if level in CEFR_ORDER else ""


def _split_joint_label(value: str) -> tuple[str, str]:
    text = str(value or "")
    if "|" not in text:
        return text.strip().upper(), ""
    cefr, grammar_class = text.split("|", 1)
    return cefr.strip().upper(), grammar_class.strip().lower()


def _feature_row(row: dict[str, Any], *, profile: str = "runtime_stable") -> dict[str, Any]:
    source_text = str(row.get("source_text") or row.get("text") or row.get("input") or "").strip()
    base_row = {
        "source_text": source_text,
        "text": source_text,
        "grammar_evidence": row.get("grammar_evidence") if isinstance(row.get("grammar_evidence"), dict) else {},
        "tam_profile": row.get("tam_profile"),
        "provenance": row.get("provenance") if isinstance(row.get("provenance"), dict) else {"dataset_source": "phase1", "treebank": "phase1"},
    }
    # Keep exactly the same feature extractor as runtime CEFR path.
    return project_feature_profile(extract_tabular_features(base_row), profile=profile)


def _build_xy(rows: list[dict[str, Any]], *, feature_profile: str) -> tuple[list[dict[str, Any]], list[str], list[str], list[str]]:
    x_rows: list[dict[str, Any]] = []
    y_joint: list[str] = []
    y_cefr: list[str] = []
    y_class: list[str] = []
    for row in rows:
        cefr = _normalize_cefr(row.get("cefr_label") or row.get("cefr_level"))
        if not cefr:
            continue
        class_id = _primary_class(row)
        if not class_id:
            continue
        x_rows.append(_feature_row(row, profile=feature_profile))
        y_joint.append(f"{cefr}|{class_id}")
        y_cefr.append(cefr)
        y_class.append(class_id)
    if not x_rows:
        raise ValueError("No valid rows for joint tabular training.")
    return x_rows, y_joint, y_cefr, y_class


def train_tabular_joint_profile(
    *,
    train_path: str,
    dev_path: str,
    test_path: str,
    output_dir: str,
    feature_profile: str = "runtime_stable",
    seed: int = 42,
) -> dict[str, Any]:
    train_rows = _load_jsonl(train_path)
    dev_rows = _load_jsonl(dev_path)
    test_rows = _load_jsonl(test_path)

    x_train, y_train_joint, y_train_cefr, _ = _build_xy(train_rows, feature_profile=feature_profile)
    x_dev, y_dev_joint, y_dev_cefr, y_dev_class = _build_xy(dev_rows, feature_profile=feature_profile)
    x_test, y_test_joint, y_test_cefr, y_test_class = _build_xy(test_rows, feature_profile=feature_profile)

    model = Pipeline(
        steps=[
            ("vectorizer", DictVectorizer(sparse=False)),
            (
                "classifier",
                RandomForestClassifier(
                    n_estimators=700,
                    max_depth=None,
                    min_samples_leaf=1,
                    class_weight="balanced_subsample",
                    n_jobs=-1,
                    random_state=seed,
                ),
            ),
        ]
    )
    model.fit(x_train, y_train_joint)

    dev_pred_joint = [str(item) for item in model.predict(x_dev)]
    test_pred_joint = [str(item) for item in model.predict(x_test)]

    dev_pred_cefr, dev_pred_class = zip(*[_split_joint_label(item) for item in dev_pred_joint])
    test_pred_cefr, test_pred_class = zip(*[_split_joint_label(item) for item in test_pred_joint])

    report = {
        "feature_profile": feature_profile,
        "train_rows": len(x_train),
        "dev_rows": len(x_dev),
        "test_rows": len(x_test),
        "train_cefr_distribution": dict(sorted(Counter(y_train_cefr).items())),
        "dev_cefr_distribution": dict(sorted(Counter(y_dev_cefr).items())),
        "test_cefr_distribution": dict(sorted(Counter(y_test_cefr).items())),
        "joint_dev_accuracy": float(accuracy_score(y_dev_joint, dev_pred_joint)),
        "joint_test_accuracy": float(accuracy_score(y_test_joint, test_pred_joint)),
        "cefr_dev_accuracy": float(accuracy_score(y_dev_cefr, dev_pred_cefr)),
        "cefr_test_accuracy": float(accuracy_score(y_test_cefr, test_pred_cefr)),
        "cefr_dev_macro_f1": float(f1_score(y_dev_cefr, dev_pred_cefr, average="macro", zero_division=0)),
        "cefr_test_macro_f1": float(f1_score(y_test_cefr, test_pred_cefr, average="macro", zero_division=0)),
        "grammar_dev_accuracy": float(accuracy_score(y_dev_class, dev_pred_class)),
        "grammar_test_accuracy": float(accuracy_score(y_test_class, test_pred_class)),
        "grammar_dev_macro_f1": float(f1_score(y_dev_class, dev_pred_class, average="macro", zero_division=0)),
        "grammar_test_macro_f1": float(f1_score(y_test_class, test_pred_class, average="macro", zero_division=0)),
    }

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    model_path = out_dir / "best_tabular_joint_profile.joblib"
    summary_path = out_dir / "tabular_joint_profile_summary.json"
    joblib.dump(model, model_path)
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    build_classifier_metadata_from_dataset(classifier_jsonl_path=train_path, output_dir=str(out_dir))
    return {
        "model_path": str(model_path),
        "summary_path": str(summary_path),
        "output_dir": str(out_dir),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Train joint tabular profile model: CEFR + grammar class.")
    parser.add_argument("--train-path", default="data/processed_classifier/phase1/train_classifier.jsonl")
    parser.add_argument("--dev-path", default="data/processed_classifier/phase1/dev_classifier.jsonl")
    parser.add_argument("--test-path", default="data/processed_classifier/phase1/test_classifier.jsonl")
    parser.add_argument("--output-dir", default="artifacts/models/tabular_joint_profile_random_forest_v1")
    parser.add_argument("--feature-profile", default="runtime_stable", choices=["full", "no_source", "runtime_stable"])
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    result = train_tabular_joint_profile(
        train_path=args.train_path,
        dev_path=args.dev_path,
        test_path=args.test_path,
        output_dir=args.output_dir,
        feature_profile=args.feature_profile,
        seed=args.seed,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
