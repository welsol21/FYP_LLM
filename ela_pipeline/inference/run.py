"""Production inference runner: spaCy -> skeleton -> TAM -> local generator -> validator."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from typing import Any

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


def _walk_nodes(node: dict):
    yield node
    for child in node.get("linguistic_elements", []) or []:
        if isinstance(child, dict):
            yield from _walk_nodes(child)


def _node_source_text(node: dict, sentence_text: str) -> str:
    span = node.get("source_span")
    if isinstance(span, dict):
        start = span.get("start")
        end = span.get("end")
        if isinstance(start, int) and isinstance(end, int):
            if 0 <= start <= end <= len(sentence_text):
                return sentence_text[start:end]
    return str(node.get("content") or "")


def _attach_translation(
    doc: dict,
    translator: Any,
    source_lang: str,
    target_lang: str,
    include_node_translations: bool = True,
) -> None:
    for sentence_node in doc.values():
        if not isinstance(sentence_node, dict):
            continue

        sentence_text = str(sentence_node.get("content") or "")
        sentence_translation = translator.translate_text(sentence_text, source_lang=source_lang, target_lang=target_lang)
        sentence_node["translation"] = {
            "source_lang": source_lang,
            "target_lang": target_lang,
            "model": getattr(translator, "model_name", "unknown"),
            "text": sentence_translation,
        }

        if not include_node_translations:
            continue

        translated_by_node_id: dict[str, str] = {}
        translated_by_source_key: dict[str, str] = {}

        def translate_node(node: dict) -> None:
            node_id = node.get("node_id")
            ref_node_id = node.get("ref_node_id")

            if isinstance(ref_node_id, str) and ref_node_id in translated_by_node_id:
                translated = translated_by_node_id[ref_node_id]
            else:
                source_text = _node_source_text(node, sentence_text)
                source_key = source_text.strip()
                if source_key in translated_by_source_key:
                    translated = translated_by_source_key[source_key]
                else:
                    translated = translator.translate_text(source_text, source_lang=source_lang, target_lang=target_lang)
                    translated_by_source_key[source_key] = translated

            node["translation"] = {
                "source_lang": source_lang,
                "target_lang": target_lang,
                "text": translated,
            }
            if isinstance(node_id, str):
                translated_by_node_id[node_id] = translated

            for child in node.get("linguistic_elements", []) or []:
                if isinstance(child, dict):
                    translate_node(child)

        for child in sentence_node.get("linguistic_elements", []) or []:
            if isinstance(child, dict):
                translate_node(child)


def run_pipeline(
    text: str,
    model_dir: str | None = None,
    spacy_model: str = "en_core_web_sm",
    validation_mode: str = "v2_strict",
    note_mode: str = "template_only",
    backoff_debug_summary: bool = False,
    enable_translation: bool = False,
    translation_provider: str = "m2m100",
    translation_model: str = "facebook/m2m100_418M",
    translation_source_lang: str = "en",
    translation_target_lang: str = "ru",
    translation_device: str = "auto",
    translate_nodes: bool = True,
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

        annotator = LocalT5Annotator(
            model_dir=model_dir,
            note_mode=note_mode,
            backoff_debug_summary=backoff_debug_summary,
        )
        annotator.annotate(enriched)

    if enable_translation:
        if translation_provider != "m2m100":
            raise ValueError("translation_provider must be 'm2m100'")
        from ela_pipeline.translate import M2M100Translator

        translator = M2M100Translator(
            model_name=translation_model,
            device=translation_device,
        )
        _attach_translation(
            enriched,
            translator=translator,
            source_lang=translation_source_lang,
            target_lang=translation_target_lang,
            include_node_translations=translate_nodes,
        )

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
    parser.add_argument(
        "--backoff-debug-summary",
        action="store_true",
        help="Attach sentence-level backoff_summary with node ids/reasons for debugging.",
    )
    parser.add_argument("--translate", action="store_true", help="Enable multilingual translation enrichment.")
    parser.add_argument(
        "--translation-provider",
        default="m2m100",
        choices=["m2m100"],
        help="Translation backend provider (extensible).",
    )
    parser.add_argument(
        "--translation-model",
        default="facebook/m2m100_418M",
        help="Hugging Face model id for translation backend.",
    )
    parser.add_argument("--translation-source-lang", default="en", help="Source language code.")
    parser.add_argument("--translation-target-lang", default="ru", help="Target language code.")
    parser.add_argument(
        "--translation-device",
        default="auto",
        choices=["auto", "cpu", "cuda"],
        help="Device for translation model execution.",
    )
    parser.add_argument(
        "--no-translate-nodes",
        action="store_true",
        help="Translate sentence only (skip phrase/word node content translation).",
    )
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    result = run_pipeline(
        text=args.text,
        model_dir=args.model_dir,
        spacy_model=args.spacy_model,
        validation_mode=args.validation_mode,
        note_mode=args.note_mode,
        backoff_debug_summary=args.backoff_debug_summary,
        enable_translation=args.translate,
        translation_provider=args.translation_provider,
        translation_model=args.translation_model,
        translation_source_lang=args.translation_source_lang,
        translation_target_lang=args.translation_target_lang,
        translation_device=args.translation_device,
        translate_nodes=not args.no_translate_nodes,
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
