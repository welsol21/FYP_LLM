"""Evaluate template classifier end-to-end: template_id -> rendered note."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    import sys

    sys.path.append(str(Path(__file__).resolve().parents[2]))

from ela_pipeline.annotate.template_registry import (
    is_template_semantically_compatible,
    render_template_note,
)
from ela_pipeline.classifier.evaluate_deberta_classifier import evaluate_rows


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
                    out.append(row)
    return out


def _build_stub(row: dict[str, Any], *, template_id: str | None = None) -> dict[str, Any]:
    level = str(row.get("level") or "").strip()
    content = str(row.get("target_content") or row.get("sentence_text") or "").strip()
    tid = str(template_id or row.get("template_id") or "").strip().upper()

    if level == "Sentence":
        return {
            "type": "Sentence",
            "content": content or str(row.get("sentence_text") or "").strip(),
            "part_of_speech": "sentence",
            "grammatical_role": "clause",
            "dep_label": "clause",
            "tense": "null",
            "aspect": "null",
            "mood": "null",
            "voice": "null",
            "finiteness": "null",
        }

    pos = "phrase"
    role = "dep"
    if tid.startswith(("PHRASE_PP_", "PP_")):
        pos = "prepositional phrase"
        role = "modifier"
    elif tid.startswith(("PHRASE_RELATIVE_CLAUSE",)):
        pos = "relative clause"
        role = "modifier"
    elif tid.startswith(("PHRASE_VP_", "VP_")):
        pos = "verb phrase"
        role = "predicate"
    elif tid.startswith(("NP_",)):
        pos = "noun phrase"
        role = "object"

    return {
        "type": "Phrase",
        "content": content,
        "part_of_speech": pos,
        "grammatical_role": role,
        "dep_label": role,
        "tense": "null",
        "aspect": "null",
        "mood": "null",
        "voice": "null",
        "finiteness": "null",
    }


def evaluate_template_classifier_inference(
    *,
    dataset_path: str,
    model_path: str,
    output_path: str = "",
    device: str = "cuda",
) -> dict[str, Any]:
    try:
        from transformers import pipeline
    except Exception as exc:  # pragma: no cover
        raise ImportError("transformers is required for template-classifier inference evaluation") from exc

    if str(device).strip().lower() != "cuda":
        raise RuntimeError("GPU-only policy: evaluation supports only device='cuda'")

    try:
        import torch
    except Exception as exc:  # pragma: no cover
        raise ImportError("torch is required for template-classifier inference evaluation") from exc

    if not torch.cuda.is_available():
        raise RuntimeError("GPU-only policy: CUDA is required for template-classifier inference evaluation")

    rows = _load_jsonl(dataset_path)
    clf = pipeline("text-classification", model=model_path, tokenizer=model_path, device=0, truncation=True)

    def predict_label(text: str) -> str:
        out = clf(text)
        if isinstance(out, list) and out and isinstance(out[0], dict):
            return str(out[0].get("label") or "")
        return ""

    label_metrics = evaluate_rows(rows, predict_label, label_field="template_id")

    compatible = 0
    rendered_exact = 0
    note_non_empty = 0
    samples = 0
    preview_exact = 0
    preview_non_empty = 0
    sample_predictions: list[dict[str, Any]] = []

    for row in rows:
        text = str(row.get("input") or "").strip()
        gold_template = str(row.get("template_id") or "").strip()
        if not text or not gold_template:
            continue

        pred_template = predict_label(text).strip()
        if not pred_template:
            continue

        stub = _build_stub(row, template_id=pred_template)
        pred_compatible = is_template_semantically_compatible(stub, pred_template)
        if pred_compatible:
            compatible += 1
        pred_note = render_template_note(pred_template, stub, "classifier_inference")
        if pred_note:
            note_non_empty += 1

        gold_stub = _build_stub(row, template_id=gold_template)
        gold_note = render_template_note(gold_template, gold_stub, "classifier_inference")
        preview_note = str(row.get("template_preview") or "").strip()
        if preview_note:
            preview_non_empty += 1
        if gold_note and preview_note and gold_note == preview_note:
            preview_exact += 1
        if pred_note and gold_note and pred_note == gold_note:
            rendered_exact += 1

        samples += 1
        if len(sample_predictions) < 25:
            sample_predictions.append(
                {
                    "level": row.get("level"),
                    "sentence_text": row.get("sentence_text"),
                    "target_content": row.get("target_content"),
                    "gold_template_id": gold_template,
                    "pred_template_id": pred_template,
                    "compatible": pred_compatible,
                    "gold_note": gold_note,
                    "pred_note": pred_note,
                    "template_preview": preview_note,
                }
            )

    result = {
        "dataset_path": dataset_path,
        "model_path": model_path,
        "device": "cuda",
        "metrics": {
            "label_accuracy": label_metrics["accuracy"],
            "label_macro_f1": label_metrics["macro_f1"],
            "label_samples": label_metrics["samples"],
            "semantic_compatibility_rate": (compatible / samples) if samples else 0.0,
            "rendered_note_exact_match": (rendered_exact / samples) if samples else 0.0,
            "rendered_note_non_empty_rate": (note_non_empty / samples) if samples else 0.0,
            "gold_renderer_matches_dataset_preview": (preview_exact / preview_non_empty) if preview_non_empty else 0.0,
        },
        "top_confusions": label_metrics.get("top_confusions") or [],
        "per_label": label_metrics.get("per_label") or {},
        "sample_predictions": sample_predictions,
    }

    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate DeBERTa template classifier end-to-end.")
    parser.add_argument("--dataset-path", required=True)
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--output-path", default="")
    parser.add_argument("--device", default="cuda", choices=["cuda"])
    args = parser.parse_args()

    result = evaluate_template_classifier_inference(
        dataset_path=args.dataset_path,
        model_path=args.model_path,
        output_path=args.output_path,
        device=args.device,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
