"""Train tabular baselines on the merged full-ladder dataset."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_score, recall_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import LinearSVC

from .metadata import build_classifier_metadata_from_dataset


CEFR_ORDER = ("A1", "A2", "B1", "B2", "C1", "C2")
FEATURE_PROFILES = ("full", "no_source", "runtime_stable")


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


def _normalize_label(value: Any, *, label_field: str) -> str:
    label = str(value or "").strip()
    if not label:
        return ""
    if label_field == "cefr_label":
        upper = label.upper()
        return upper if upper in CEFR_ORDER else ""
    return label.lower()


def _safe_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def extract_tabular_features(row: dict[str, Any]) -> dict[str, Any]:
    text = str(row.get("source_text") or row.get("text") or row.get("input") or "").strip()
    evidence = row.get("grammar_evidence") if isinstance(row.get("grammar_evidence"), dict) else {}
    dep_signature = _safe_list(evidence.get("dep_signature"))
    pos_signature = _safe_list(evidence.get("pos_signature"))
    grammar_classes = _safe_list(row.get("grammar_classes"))
    provenance = row.get("provenance") if isinstance(row.get("provenance"), dict) else {}

    feature_row: dict[str, Any] = {
        "word_count": len(text.split()),
        "char_count": len(text),
        "token_count": int(evidence.get("token_count") or 0),
        "dep_count": len(dep_signature),
        "dep_unique_count": len(set(dep_signature)),
        "pos_count": len(pos_signature),
        "pos_unique_count": len(set(pos_signature)),
        "grammar_class_count": len(grammar_classes),
        "tam_profile": str(row.get("tam_profile") or "").strip().lower(),
        "dataset_source": str(provenance.get("dataset_source") or "").strip().lower(),
        "treebank": str(provenance.get("treebank") or "").strip(),
        "dep_signature_join": "|".join(dep_signature),
        "pos_signature_join": "|".join(pos_signature),
        "has_relative_clause_marker": int(any(dep in {"acl:relcl"} for dep in dep_signature)),
        "has_clause_embedding": int(any(dep in {"ccomp", "xcomp", "advcl", "acl", "acl:relcl", "parataxis"} for dep in dep_signature)),
        "has_passive_signal": int("aux:pass" in dep_signature or "nsubj:pass" in dep_signature),
    }
    return feature_row


def project_feature_profile(features: dict[str, Any], *, profile: str = "full") -> dict[str, Any]:
    selected = str(profile or "full").strip().lower()
    if selected not in FEATURE_PROFILES:
        raise ValueError(f"Unknown feature profile: {selected}")
    if selected == "full":
        return dict(features)
    if selected == "no_source":
        return {
            key: value
            for key, value in features.items()
            if key not in {"dataset_source", "treebank"}
        }
    return {
        key: features[key]
        for key in (
            "word_count",
            "char_count",
            "token_count",
            "dep_count",
            "dep_unique_count",
            "pos_count",
            "pos_unique_count",
            "grammar_class_count",
            "tam_profile",
            "has_relative_clause_marker",
            "has_clause_embedding",
            "has_passive_signal",
            "dep_signature_join",
            "pos_signature_join",
        )
        if key in features
    }


def build_feature_rows(
    rows: list[dict[str, Any]],
    *,
    label_field: str = "cefr_label",
    feature_profile: str = "runtime_stable",
) -> tuple[list[dict[str, Any]], list[str]]:
    feature_rows: list[dict[str, Any]] = []
    labels: list[str] = []
    for row in rows:
        raw_value = row.get(label_field)
        if raw_value in (None, "") and label_field == "cefr_label":
            raw_value = row.get("cefr_level")
        label = _normalize_label(raw_value, label_field=label_field)
        if not label:
            continue
        feature_rows.append(project_feature_profile(extract_tabular_features(row), profile=feature_profile))
        labels.append(label)
    if not feature_rows:
        raise ValueError(f"No valid '{label_field}' rows found for baseline")
    return feature_rows, labels


def evaluate_predictions(y_true: list[str], y_pred: list[str], *, label_order: list[str] | None = None) -> dict[str, Any]:
    if label_order:
        labels = [label for label in label_order if label in set(y_true) | set(y_pred)]
    else:
        labels = sorted(set(y_true) | set(y_pred))
    cm = confusion_matrix(y_true, y_pred, labels=labels)
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "macro_f1": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
        "macro_precision": float(precision_score(y_true, y_pred, average="macro", zero_division=0)),
        "macro_recall": float(recall_score(y_true, y_pred, average="macro", zero_division=0)),
        "labels": labels,
        "confusion": {
            labels[i]: {labels[j]: int(cm[i, j]) for j in range(len(labels))}
            for i in range(len(labels))
        },
    }


def _make_models(seed: int) -> dict[str, Pipeline]:
    return {
        "logreg": Pipeline(
            steps=[
                ("vectorizer", DictVectorizer(sparse=False)),
                ("scaler", StandardScaler()),
                (
                    "classifier",
                    LogisticRegression(
                        max_iter=4000,
                        class_weight="balanced",
                        multi_class="multinomial",
                        random_state=seed,
                    ),
                ),
            ]
        ),
        "linear_svc": Pipeline(
            steps=[
                ("vectorizer", DictVectorizer(sparse=False)),
                ("scaler", StandardScaler()),
                ("classifier", LinearSVC(class_weight="balanced", random_state=seed)),
            ]
        ),
        "random_forest": Pipeline(
            steps=[
                ("vectorizer", DictVectorizer(sparse=False)),
                (
                    "classifier",
                    RandomForestClassifier(
                        n_estimators=120,
                        max_depth=24,
                        min_samples_leaf=2,
                        class_weight="balanced_subsample",
                        random_state=seed,
                        n_jobs=-1,
                    ),
                ),
            ]
        ),
    }


def train_tabular_cefr_baseline(
    *,
    train_path: str,
    dev_path: str,
    test_path: str,
    output_dir: str,
    model_names: list[str] | None = None,
    seed: int = 42,
    label_field: str = "cefr_label",
    feature_profile: str = "runtime_stable",
) -> dict[str, Any]:
    train_rows = _load_jsonl(train_path)
    dev_rows = _load_jsonl(dev_path)
    test_rows = _load_jsonl(test_path)

    x_train, y_train = build_feature_rows(train_rows, label_field=label_field, feature_profile=feature_profile)
    x_dev, y_dev = build_feature_rows(dev_rows, label_field=label_field, feature_profile=feature_profile)
    x_test, y_test = build_feature_rows(test_rows, label_field=label_field, feature_profile=feature_profile)

    models = _make_models(seed)
    selected_names = list(model_names or models.keys())
    unknown = sorted(set(selected_names) - set(models.keys()))
    if unknown:
        raise ValueError(f"Unknown baseline model(s): {unknown}")
    models = {name: models[name] for name in selected_names}
    results: dict[str, Any] = {}
    best_name = ""
    best_score = -1.0
    best_model: Any = None

    label_order = list(CEFR_ORDER) if label_field == "cefr_label" else sorted(set(y_train) | set(y_dev) | set(y_test))

    for name, model in models.items():
        model.fit(x_train, y_train)
        dev_pred = model.predict(x_dev)
        test_pred = model.predict(x_test)
        dev_metrics = evaluate_predictions(
            y_dev,
            dev_pred.tolist() if isinstance(dev_pred, np.ndarray) else list(dev_pred),
            label_order=label_order,
        )
        test_metrics = evaluate_predictions(
            y_test,
            test_pred.tolist() if isinstance(test_pred, np.ndarray) else list(test_pred),
            label_order=label_order,
        )
        results[name] = {
            "dev": dev_metrics,
            "test": test_metrics,
        }
        if dev_metrics["macro_f1"] > best_score:
            best_score = dev_metrics["macro_f1"]
            best_name = name
            best_model = model

    if best_model is None:
        raise RuntimeError("No baseline model was trained")

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(best_model, out_dir / "best_tabular_cefr_baseline.joblib")
    metadata_path = None
    if label_field == "cefr_label":
        metadata_summary = build_classifier_metadata_from_dataset(
            classifier_jsonl_path=train_path,
            output_dir=str(out_dir),
        )
        metadata_path = metadata_summary["metadata_path"]

    summary = {
        "train_path": train_path,
        "dev_path": dev_path,
        "test_path": test_path,
        "label_field": label_field,
        "feature_profile": feature_profile,
        "train_samples": len(x_train),
        "dev_samples": len(x_dev),
        "test_samples": len(x_test),
        "train_label_counts": dict(sorted(Counter(y_train).items())),
        "models": results,
        "best_model": best_name,
        "best_dev_macro_f1": best_score,
        "best_model_path": str(out_dir / "best_tabular_cefr_baseline.joblib"),
        "classifier_metadata_path": metadata_path,
    }
    (out_dir / "tabular_cefr_baseline_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Train tabular baselines on full-ladder dataset.")
    parser.add_argument("--train-path", default="artifacts/classifier_full_ladder_dataset/train_classifier.jsonl")
    parser.add_argument("--dev-path", default="artifacts/classifier_full_ladder_dataset/dev_classifier.jsonl")
    parser.add_argument("--test-path", default="artifacts/classifier_full_ladder_dataset/test_classifier.jsonl")
    parser.add_argument("--output-dir", default="artifacts/models/tabular_cefr_baseline")
    parser.add_argument("--model", action="append", default=[], help="Model name to run. Can be passed multiple times.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--label-field", default="cefr_label")
    parser.add_argument("--feature-profile", default="runtime_stable", choices=list(FEATURE_PROFILES))
    args = parser.parse_args()

    summary = train_tabular_cefr_baseline(
        train_path=args.train_path,
        dev_path=args.dev_path,
        test_path=args.test_path,
        output_dir=args.output_dir,
        model_names=args.model or None,
        seed=args.seed,
        label_field=args.label_field,
        feature_profile=args.feature_profile,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
