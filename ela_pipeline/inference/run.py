"""Production inference runner: spaCy -> skeleton -> TAM -> local generator -> validator."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime

from ela_pipeline.contract import deep_copy_contract
from ela_pipeline.parse.spacy_parser import load_nlp
from ela_pipeline.skeleton.builder import build_skeleton
from ela_pipeline.tam.rules import apply_tam
from ela_pipeline.validation.validator import (
    raise_if_invalid,
    validate_contract,
    validate_frozen_structure,
)

STRICT_NULLABLE_TAM_FIELDS = {"tense", "aspect", "mood", "voice", "finiteness"}


def _normalize_strict_null_sentinels(node: dict) -> None:
    for field in STRICT_NULLABLE_TAM_FIELDS:
        if node.get(field) == "null":
            node[field] = None
    features = node.get("features")
    if isinstance(features, dict):
        for key, value in list(features.items()):
            if value == "null":
                features[key] = None
    for child in node.get("linguistic_elements", []):
        if isinstance(child, dict):
            _normalize_strict_null_sentinels(child)


def _apply_strict_null_normalization(doc: dict, validation_mode: str) -> None:
    if validation_mode != "v2_strict":
        return
    for sentence_node in doc.values():
        if isinstance(sentence_node, dict):
            _normalize_strict_null_sentinels(sentence_node)


def run_pipeline(
    text: str,
    model_dir: str | None = None,
    spacy_model: str = "en_core_web_sm",
    validation_mode: str = "v2_strict",
    note_mode: str = "template_only",
) -> dict:
    nlp = load_nlp(spacy_model)

    skeleton = build_skeleton(text, nlp)
    _apply_strict_null_normalization(skeleton, validation_mode)
    raise_if_invalid(validate_contract(skeleton, validation_mode=validation_mode))

    enriched = deep_copy_contract(skeleton)
    apply_tam(enriched, nlp)
    _apply_strict_null_normalization(enriched, validation_mode)

    if model_dir:
        from ela_pipeline.annotate.local_generator import LocalT5Annotator

        annotator = LocalT5Annotator(model_dir=model_dir, note_mode=note_mode)
        annotator.annotate(enriched)

    raise_if_invalid(validate_contract(enriched, validation_mode=validation_mode))
    raise_if_invalid(validate_frozen_structure(skeleton, enriched))
    return enriched


def main() -> None:
    parser = argparse.ArgumentParser(description="Run full ELA inference pipeline")
    parser.add_argument("--text", required=True)
    parser.add_argument("--model-dir", default=None)
    parser.add_argument("--spacy-model", default="en_core_web_sm")
    parser.add_argument("--validation-mode", default="v2_strict", choices=["v1", "v2_strict"])
    parser.add_argument(
        "--note-mode",
        default="template_only",
        choices=["template_only", "llm", "hybrid", "two_stage"],
        help="Inference mode: template_only, llm, hybrid, or two_stage (model template_id -> rule note render).",
    )
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    result = run_pipeline(
        text=args.text,
        model_dir=args.model_dir,
        spacy_model=args.spacy_model,
        validation_mode=args.validation_mode,
        note_mode=args.note_mode,
    )

    out_path = args.output
    if out_path is None:
        os.makedirs("inference_results", exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        out_path = os.path.join("inference_results", f"pipeline_result_{ts}.json")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"Saved: {out_path}")


if __name__ == "__main__":
    main()
