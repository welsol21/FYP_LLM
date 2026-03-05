"""Train a single RandomForest that predicts CEFR + grammar class jointly."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from typing import Any

import joblib
from sklearn.feature_extraction import DictVectorizer
from sklearn.metrics import accuracy_score, f1_score
from sklearn.pipeline import Pipeline
import numpy as np

from .dataset_protocol import canonicalize_grammar_classes, normalize_classifier_row
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
                row = json.loads(line)
                if isinstance(row, dict):
                    row = normalize_classifier_row(row)
                out.append(row)
    return out


def _primary_class(row: dict[str, Any]) -> str:
    classes = canonicalize_grammar_classes(row.get("grammar_classes"))
    if not classes:
        grammar_label = str(row.get("grammar_label") or "").strip().lower()
        if grammar_label:
            classes = canonicalize_grammar_classes(grammar_label.split("|"))
    if not classes:
        return ""
    return str(classes[0]).strip().lower()


def _normalize_cefr(value: Any) -> str:
    level = str(value or "").strip().upper()
    return level if level in CEFR_ORDER else ""


def _split_joint_label(value: str) -> tuple[str, str]:
    text = str(value or "")
    if "|" not in text:
        return text.strip().upper(), ""
    cefr, grammar_class = text.split("|", 1)
    return cefr.strip().upper(), grammar_class.strip().lower()


def _assert_gpu_training_available() -> None:
    try:
        import xgboost as xgb
    except Exception as exc:
        raise ImportError("xgboost is required for GPU tabular training") from exc
    build_info = xgb.build_info()
    if not bool(build_info.get("USE_CUDA")):
        raise RuntimeError("GPU-only policy: installed xgboost was built without CUDA support.")


def _assert_model_trained_on_gpu(model: Any, model_name: str) -> None:
    classifier = model
    if hasattr(model, "named_steps") and isinstance(model.named_steps, dict):
        classifier = model.named_steps.get("classifier", model)
    if not hasattr(classifier, "get_booster"):
        return
    try:
        booster_cfg = json.loads(classifier.get_booster().save_config())
    except Exception:
        return
    device = (
        booster_cfg.get("learner", {})
        .get("generic_param", {})
        .get("device", "")
        .lower()
    )
    if not device.startswith("cuda"):
        raise RuntimeError(
            f"GPU-only policy violated: model '{model_name}' trained on device='{device or 'unknown'}'."
        )


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

    _assert_gpu_training_available()
    joint_label_order = sorted(set(y_train_joint) | set(y_dev_joint) | set(y_test_joint))
    joint_to_id = {label: idx for idx, label in enumerate(joint_label_order)}
    id_to_joint = {idx: label for label, idx in joint_to_id.items()}
    y_train_ids = [joint_to_id[label] for label in y_train_joint]
    y_dev_ids = [joint_to_id[label] for label in y_dev_joint]
    y_test_ids = [joint_to_id[label] for label in y_test_joint]

    try:
        from xgboost import XGBClassifier
    except Exception as exc:
        raise ImportError("xgboost is required for GPU tabular training") from exc

    model = Pipeline(
        steps=[
            ("vectorizer", DictVectorizer(sparse=False)),
            (
                "classifier",
                XGBClassifier(
                    objective="multi:softmax",
                    num_class=int(len(joint_label_order)),
                    n_estimators=800,
                    max_depth=10,
                    learning_rate=0.06,
                    subsample=0.9,
                    colsample_bytree=0.9,
                    reg_lambda=1.0,
                    random_state=seed,
                    tree_method="hist",
                    device="cuda",
                    eval_metric="mlogloss",
                ),
            ),
        ]
    )
    model.fit(x_train, y_train_ids)
    _assert_model_trained_on_gpu(model, "xgboost_joint_gpu")

    dev_pred_ids = model.predict(x_dev)
    test_pred_ids = model.predict(x_test)
    dev_pred_joint = [id_to_joint[int(x)] for x in (dev_pred_ids.tolist() if isinstance(dev_pred_ids, np.ndarray) else list(dev_pred_ids))]
    test_pred_joint = [id_to_joint[int(x)] for x in (test_pred_ids.tolist() if isinstance(test_pred_ids, np.ndarray) else list(test_pred_ids))]

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
    metadata_path = out_dir / "classifier_metadata.json"
    if metadata_path.is_file():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if isinstance(metadata, dict):
            metadata["joint_label_order"] = list(joint_label_order)
            metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
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
    parser.add_argument("--output-dir", default="artifacts/models/tabular_joint_profile_full_ladder_xgboost_gpu_v2")
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
