"""Train GPU-only XGBoost tabular CEFR baseline on the merged full-ladder dataset."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from typing import Any
import re

import joblib
import numpy as np
from sklearn.feature_extraction import DictVectorizer
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_score, recall_score
from sklearn.pipeline import Pipeline

from .metadata import build_classifier_metadata_from_dataset


CEFR_ORDER = ("A1", "A2", "B1", "B2", "C1", "C2")
FEATURE_PROFILES = ("full", "no_source", "runtime_stable")
PLACEHOLDER_PATTERN = re.compile(r"\{\{([A-Z0-9_]+)\}\}")
CONTRACT_PROMPT_RE = re.compile(r"^task:\s*(?P<task>[^ ]+)\s+payload:\s*(?P<payload>\{.*\})\s*$", re.DOTALL)


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


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _parse_contract_prompt(text: str) -> dict[str, Any]:
    match = CONTRACT_PROMPT_RE.match(text.strip())
    if not match:
        return {}
    try:
        payload = json.loads(match.group("payload"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    parsed = dict(payload)
    parsed["task"] = str(parsed.get("task") or match.group("task") or "").strip()
    return parsed


def extract_tabular_features(row: dict[str, Any]) -> dict[str, Any]:
    text = str(row.get("source_text") or row.get("text") or row.get("input") or "").strip()
    contract_payload = _parse_contract_prompt(text)
    normalized_text = " ".join(part for part in text.lower().split() if part)
    tokens = [part for part in normalized_text.split(" ") if part]
    bigrams = [f"{tokens[i]}_{tokens[i+1]}" for i in range(max(0, len(tokens) - 1))]
    evidence = row.get("grammar_evidence") if isinstance(row.get("grammar_evidence"), dict) else {}
    dep_signature = _safe_list(evidence.get("dep_signature"))
    pos_signature = _safe_list(evidence.get("pos_signature"))
    grammar_classes = _safe_list(row.get("grammar_classes"))
    provenance = row.get("provenance") if isinstance(row.get("provenance"), dict) else {}
    placeholder_names = PLACEHOLDER_PATTERN.findall(text)
    token_counter = Counter(tokens)
    bigram_counter = Counter(bigrams)
    placeholder_counter = Counter(placeholder_names)
    prompt_context = _safe_dict(contract_payload.get("context"))
    node_context = _safe_dict(prompt_context.get("node_context"))
    parent_context = _safe_dict(prompt_context.get("parent_context"))
    sentence_context = _safe_dict(prompt_context.get("sentence_context"))
    children_summary = _safe_dict(prompt_context.get("children_summary"))
    selection = _safe_dict(contract_payload.get("selection"))
    slot_values = _safe_dict(contract_payload.get("slot_values"))
    path_types = _safe_list(prompt_context.get("path_types"))
    child_types = _safe_list(children_summary.get("types"))
    child_pos = _safe_list(children_summary.get("part_of_speech"))
    child_roles = _safe_list(children_summary.get("grammatical_role"))
    sentence_text = str(sentence_context.get("sentence_text") or row.get("sentence_text") or "").strip()
    sentence_norm = " ".join(part for part in sentence_text.lower().split() if part)
    sentence_tokens = [part for part in sentence_norm.split(" ") if part]
    sentence_bigrams = [f"{sentence_tokens[i]}_{sentence_tokens[i+1]}" for i in range(max(0, len(sentence_tokens) - 1))]
    sentence_token_counter = Counter(sentence_tokens)
    sentence_bigram_counter = Counter(sentence_bigrams)

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
        "first_token": tokens[0] if tokens else "",
        "second_token": tokens[1] if len(tokens) > 1 else "",
        "last_token": tokens[-1] if tokens else "",
        "first_bigram": bigrams[0] if bigrams else "",
        "last_bigram": bigrams[-1] if bigrams else "",
        "has_modal_should": int("should" in tokens),
        "has_modal_would": int("would" in tokens),
        "has_modal_could": int("could" in tokens),
        "has_modal_must": int("must" in tokens),
        "has_modal_might": int("might" in tokens),
        "has_modal_may": int("may" in tokens),
        "has_modal_can": int("can" in tokens),
        "has_have_aux": int("have" in tokens or "has" in tokens or "had" in tokens),
        "has_be_aux": int(any(tok in {"am", "is", "are", "was", "were", "be", "been", "being"} for tok in tokens)),
        "has_ing_form": int(any(tok.endswith("ing") for tok in tokens)),
        "has_ed_form": int(any(tok.endswith("ed") for tok in tokens)),
        "has_before_after": int(any(tok in {"before", "after"} for tok in tokens)),
        "has_if_when_while": int(any(tok in {"if", "when", "while"} for tok in tokens)),
        "ends_with_question": int(text.endswith("?")),
        "placeholder_count": len(placeholder_names),
        "placeholder_unique_count": len(set(placeholder_names)),
        "placeholder_signature_join": "|".join(placeholder_names),
        "token_signature_join": "|".join(tokens),
        "bigram_signature_join": "|".join(bigrams),
        "is_contract_prompt": int(bool(contract_payload)),
        "contract_task": str(contract_payload.get("task") or "").strip().lower(),
        "contract_prompt_template_version": str(contract_payload.get("prompt_template_version") or row.get("prompt_template_version") or "").strip().lower(),
        "contract_node_level": str(contract_payload.get("node_level") or "").strip().lower(),
        "contract_note_template_version": str(contract_payload.get("note_template_version") or "").strip().lower(),
        "contract_selection_template_id": str(selection.get("template_id") or row.get("template_id") or "").strip(),
        "contract_selection_level": str(selection.get("level") or "").strip().lower(),
        "contract_selection_key_l1": str(selection.get("context_key_l1") or "").strip().lower(),
        "contract_selection_key_l2": str(selection.get("context_key_l2") or "").strip().lower(),
        "contract_selection_key_l3": str(selection.get("context_key_l3") or "").strip().lower(),
        "contract_selection_matched_key": str(selection.get("matched_key") or "").strip().lower(),
        "contract_allowed_slot_count": len(_safe_list(contract_payload.get("allowed_slots"))),
        "contract_slot_value_count": len(slot_values),
        "contract_path_depth": int(prompt_context.get("depth") or 0),
        "contract_sibling_index": int(prompt_context.get("sibling_index") or 0),
        "contract_sibling_count": int(prompt_context.get("sibling_count") or 0),
        "contract_path_types_join": "|".join(path_types),
        "contract_node_type": str(prompt_context.get("node_type") or "").strip().lower(),
        "contract_node_pos": str(node_context.get("part_of_speech") or "").strip().lower(),
        "contract_node_role": str(node_context.get("grammatical_role") or "").strip().lower(),
        "contract_node_tam": str(node_context.get("tam_construction") or "").strip().lower(),
        "contract_node_cefr": str(node_context.get("cefr_level") or "").strip().upper(),
        "contract_node_grammar_classes_join": "|".join(_safe_list(node_context.get("grammar_class_ids"))),
        "contract_parent_pos": str(parent_context.get("part_of_speech") or "").strip().lower(),
        "contract_parent_role": str(parent_context.get("grammatical_role") or "").strip().lower(),
        "contract_child_count": int(children_summary.get("count") or 0),
        "contract_child_types_join": "|".join(child_types),
        "contract_child_pos_join": "|".join(child_pos),
        "contract_child_roles_join": "|".join(child_roles),
        "sentence_word_count": len(sentence_tokens),
        "sentence_char_count": len(sentence_text),
        "sentence_first_token": sentence_tokens[0] if sentence_tokens else "",
        "sentence_last_token": sentence_tokens[-1] if sentence_tokens else "",
        "sentence_bigram_first": sentence_bigrams[0] if sentence_bigrams else "",
        "sentence_bigram_last": sentence_bigrams[-1] if sentence_bigrams else "",
        "has_if_in_sentence": int("if" in sentence_tokens),
        "has_why_in_sentence": int("why" in sentence_tokens),
        "has_that_in_sentence": int("that" in sentence_tokens),
        "has_not_in_sentence": int("not" in sentence_tokens or "n't" in sentence_norm),
        "has_question_mark_sentence": int(sentence_text.endswith("?")),
    }
    for idx, tok in enumerate(tokens[:8]):
        feature_row[f"tok_{idx}"] = tok
    for idx, bg in enumerate(bigrams[:6]):
        feature_row[f"bg_{idx}"] = bg
    for tok, count in token_counter.items():
        feature_row[f"tok_count::{tok}"] = int(count)
    for bg, count in bigram_counter.items():
        feature_row[f"bg_count::{bg}"] = int(count)
    for name, count in placeholder_counter.items():
        feature_row[f"ph_count::{name}"] = int(count)
    for tok, count in sentence_token_counter.items():
        feature_row[f"sent_tok_count::{tok}"] = int(count)
    for bg, count in sentence_bigram_counter.items():
        feature_row[f"sent_bg_count::{bg}"] = int(count)
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
            "placeholder_count",
            "placeholder_unique_count",
            "placeholder_signature_join",
            "token_signature_join",
            "bigram_signature_join",
            "is_contract_prompt",
            "contract_task",
            "contract_prompt_template_version",
            "contract_node_level",
            "contract_note_template_version",
            "contract_selection_template_id",
            "contract_selection_level",
            "contract_selection_key_l1",
            "contract_selection_key_l2",
            "contract_selection_key_l3",
            "contract_selection_matched_key",
            "contract_allowed_slot_count",
            "contract_slot_value_count",
            "contract_path_depth",
            "contract_sibling_index",
            "contract_sibling_count",
            "contract_path_types_join",
            "contract_node_type",
            "contract_node_pos",
            "contract_node_role",
            "contract_node_tam",
            "contract_node_cefr",
            "contract_node_grammar_classes_join",
            "contract_parent_pos",
            "contract_parent_role",
            "contract_child_count",
            "contract_child_types_join",
            "contract_child_pos_join",
            "contract_child_roles_join",
            "sentence_word_count",
            "sentence_char_count",
            "sentence_first_token",
            "sentence_last_token",
            "sentence_bigram_first",
            "sentence_bigram_last",
            "has_if_in_sentence",
            "has_why_in_sentence",
            "has_that_in_sentence",
            "has_not_in_sentence",
            "has_question_mark_sentence",
            "first_token",
            "second_token",
            "last_token",
            "first_bigram",
            "last_bigram",
            "has_modal_should",
            "has_modal_would",
            "has_modal_could",
            "has_modal_must",
            "has_modal_might",
            "has_modal_may",
            "has_modal_can",
            "has_have_aux",
            "has_be_aux",
            "has_ing_form",
            "has_ed_form",
            "has_before_after",
            "has_if_when_while",
            "ends_with_question",
            "tok_0",
            "tok_1",
            "tok_2",
            "tok_3",
            "tok_4",
            "tok_5",
            "tok_6",
            "tok_7",
            "bg_0",
            "bg_1",
            "bg_2",
            "bg_3",
            "bg_4",
            "bg_5",
        )
        if key in features
    } | {
        key: value
        for key, value in features.items()
        if key.startswith("tok_count::")
        or key.startswith("bg_count::")
        or key.startswith("ph_count::")
        or key.startswith("sent_tok_count::")
        or key.startswith("sent_bg_count::")
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


def _assert_gpu_training_available() -> None:
    try:
        import xgboost as xgb
    except Exception as exc:
        raise ImportError("xgboost is required for GPU tabular training") from exc
    build_info = xgb.build_info()
    if not bool(build_info.get("USE_CUDA")):
        raise RuntimeError("GPU-only policy: installed xgboost was built without CUDA support.")


def _assert_model_trained_on_gpu(model: Any, model_name: str) -> None:
    """Fail hard if XGBoost silently fell back to CPU."""
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


def _make_models(seed: int, *, num_classes: int) -> dict[str, Pipeline]:
    try:
        from xgboost import XGBClassifier
    except Exception as exc:
        raise ImportError("xgboost is required for GPU tabular training") from exc

    return {
        "xgboost_gpu": Pipeline(
            steps=[
                ("vectorizer", DictVectorizer(sparse=False)),
                (
                    "classifier",
                    XGBClassifier(
                        objective="multi:softprob",
                        num_class=int(num_classes),
                        n_estimators=600,
                        max_depth=8,
                        learning_rate=0.05,
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

    _assert_gpu_training_available()
    label_order = list(CEFR_ORDER) if label_field == "cefr_label" else sorted(set(y_train) | set(y_dev) | set(y_test))
    label_to_id = {label: idx for idx, label in enumerate(label_order)}
    id_to_label = {idx: label for label, idx in label_to_id.items()}
    y_train_ids = [label_to_id[label] for label in y_train]
    y_dev_ids = [label_to_id[label] for label in y_dev]
    y_test_ids = [label_to_id[label] for label in y_test]

    models = _make_models(seed, num_classes=len(label_order))
    selected_names = list(model_names or ["xgboost_gpu"])
    unknown = sorted(set(selected_names) - set(models.keys()))
    if unknown:
        raise ValueError(f"Unknown baseline model(s): {unknown}")
    models = {name: models[name] for name in selected_names}
    results: dict[str, Any] = {}
    best_name = ""
    best_score = -1.0
    best_model: Any = None

    for name, model in models.items():
        model.fit(x_train, y_train_ids)
        _assert_model_trained_on_gpu(model, name)
        dev_pred_ids = model.predict(x_dev)
        test_pred_ids = model.predict(x_test)
        dev_pred = [id_to_label[int(x)] for x in (dev_pred_ids.tolist() if isinstance(dev_pred_ids, np.ndarray) else list(dev_pred_ids))]
        test_pred = [id_to_label[int(x)] for x in (test_pred_ids.tolist() if isinstance(test_pred_ids, np.ndarray) else list(test_pred_ids))]
        dev_metrics = evaluate_predictions(
            y_dev,
            dev_pred,
            label_order=label_order,
        )
        test_metrics = evaluate_predictions(
            y_test,
            test_pred,
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
        "label_order": label_order,
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
    parser = argparse.ArgumentParser(description="Train GPU-only XGBoost tabular CEFR baseline on full-ladder dataset.")
    parser.add_argument("--train-path", default="artifacts/classifier_full_ladder_dataset/train_classifier.jsonl")
    parser.add_argument("--dev-path", default="artifacts/classifier_full_ladder_dataset/dev_classifier.jsonl")
    parser.add_argument("--test-path", default="artifacts/classifier_full_ladder_dataset/test_classifier.jsonl")
    parser.add_argument("--output-dir", default="artifacts/models/tabular_cefr_baseline")
    parser.add_argument(
        "--model",
        action="append",
        default=[],
        choices=["xgboost_gpu"],
        help="Model name to run. Only GPU model is allowed.",
    )
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
