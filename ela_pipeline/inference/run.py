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
DEFAULT_TRANSLATION_MODEL = "facebook/m2m100_418M"
DEFAULT_LOCAL_TRANSLATION_MODEL_DIR = "artifacts/models/m2m100_418M"
DEFAULT_CEFR_MODEL_PATH = "artifacts/models/t5_cefr/best_model"
CEFR_ALLOWED_LEVELS = {"A1", "A2", "B1", "B2", "C1", "C2"}


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


def _attach_phonetic(
    doc: dict,
    transcriber: Any,
    include_node_phonetic: bool = True,
) -> None:
    for sentence_node in doc.values():
        if not isinstance(sentence_node, dict):
            continue

        sentence_text = str(sentence_node.get("content") or "")
        sentence_node["phonetic"] = {
            "uk": transcriber.transcribe_text(sentence_text, accent="uk"),
            "us": transcriber.transcribe_text(sentence_text, accent="us"),
        }

        if not include_node_phonetic:
            continue

        phonetic_by_node_id: dict[str, dict[str, str]] = {}
        phonetic_by_source_key: dict[str, dict[str, str]] = {}

        def transcribe_node(node: dict) -> None:
            node_id = node.get("node_id")
            ref_node_id = node.get("ref_node_id")

            if isinstance(ref_node_id, str) and ref_node_id in phonetic_by_node_id:
                node_phonetic = phonetic_by_node_id[ref_node_id]
            else:
                source_text = _node_source_text(node, sentence_text)
                source_key = source_text.strip()
                if source_key in phonetic_by_source_key:
                    node_phonetic = phonetic_by_source_key[source_key]
                else:
                    node_phonetic = {
                        "uk": transcriber.transcribe_text(source_text, accent="uk"),
                        "us": transcriber.transcribe_text(source_text, accent="us"),
                    }
                    phonetic_by_source_key[source_key] = node_phonetic

            node["phonetic"] = {
                "uk": node_phonetic["uk"],
                "us": node_phonetic["us"],
            }
            if isinstance(node_id, str):
                phonetic_by_node_id[node_id] = node_phonetic

            for child in node.get("linguistic_elements", []) or []:
                if isinstance(child, dict):
                    transcribe_node(child)

        for child in sentence_node.get("linguistic_elements", []) or []:
            if isinstance(child, dict):
                transcribe_node(child)


def _normalize_synonym_values(values: list[str], source_text: str, top_k: int) -> list[str]:
    normalized_source = " ".join((source_text or "").strip().lower().split())
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        candidate = " ".join(value.strip().split())
        if not candidate:
            continue
        low = candidate.lower()
        if low == normalized_source:
            continue
        if low in seen:
            continue
        seen.add(low)
        out.append(candidate)
        if len(out) >= top_k:
            break
    return out


_VERB_PARTICLE_MAP = {
    "bank": "on",
    "rely": "on",
    "count": "on",
    "depend": "on",
}

_IRREGULAR_PAST_PARTICIPLE = {
    "be": "been",
    "become": "become",
    "begin": "begun",
    "break": "broken",
    "bring": "brought",
    "buy": "bought",
    "come": "come",
    "do": "done",
    "drink": "drunk",
    "drive": "driven",
    "eat": "eaten",
    "fall": "fallen",
    "feel": "felt",
    "find": "found",
    "get": "gotten",
    "give": "given",
    "go": "gone",
    "know": "known",
    "leave": "left",
    "make": "made",
    "read": "read",
    "run": "run",
    "say": "said",
    "see": "seen",
    "speak": "spoken",
    "swear": "sworn",
    "take": "taken",
    "write": "written",
}


def _to_past_participle(lemma: str) -> str:
    base = (lemma or "").strip().lower()
    if not base:
        return base
    if base in _IRREGULAR_PAST_PARTICIPLE:
        return _IRREGULAR_PAST_PARTICIPLE[base]
    if base.endswith("e"):
        return f"{base}d"
    if len(base) > 1 and base.endswith("y") and base[-2] not in "aeiou":
        return f"{base[:-1]}ied"
    return f"{base}ed"


def _postprocess_synonyms_for_node(node: dict, raw_synonyms: list[str], source_text: str) -> list[str]:
    pos = str(node.get("part_of_speech") or "").strip().lower()
    features = node.get("features") if isinstance(node.get("features"), dict) else {}
    verb_form = str(features.get("verb_form") or "").strip().lower()
    tense_feature = str(features.get("tense_feature") or "").strip().lower()

    out: list[str] = []
    for value in raw_synonyms:
        if not isinstance(value, str):
            continue
        candidate = " ".join(value.strip().split()).lower()
        if not candidate:
            continue

        if pos == "verb":
            tokens = candidate.split()
            head = tokens[0]
            # Expand known phrasal-verb heads to reduce out-of-context bare lemmas (e.g., bank -> bank on).
            if head in _VERB_PARTICLE_MAP and len(tokens) == 1:
                candidate = f"{head} {_VERB_PARTICLE_MAP[head]}"
                tokens = candidate.split()
                head = tokens[0]
            # Align with source non-finite past participle form when available.
            if verb_form == "part" and tense_feature == "past":
                inflected = _to_past_participle(head)
                candidate = " ".join([inflected, *tokens[1:]])

        out.append(candidate)

    return _normalize_synonym_values(out, source_text, top_k=max(1, len(out) or 1))


def _attach_synonyms(
    doc: dict,
    provider: Any,
    top_k: int = 5,
    include_node_synonyms: bool = True,
) -> None:
    k = max(1, int(top_k))
    for sentence_node in doc.values():
        if not isinstance(sentence_node, dict):
            continue

        sentence_text = str(sentence_node.get("content") or "")
        sentence_pos = sentence_node.get("part_of_speech")
        sentence_raw = provider.get_synonyms(sentence_text, pos=sentence_pos, top_k=k)
        sentence_node["synonyms"] = _normalize_synonym_values(sentence_raw, sentence_text, k)

        if not include_node_synonyms:
            continue

        synonyms_by_node_id: dict[str, list[str]] = {}
        synonyms_by_source_key: dict[str, list[str]] = {}

        def enrich_node(node: dict) -> None:
            node_id = node.get("node_id")
            ref_node_id = node.get("ref_node_id")

            if isinstance(ref_node_id, str) and ref_node_id in synonyms_by_node_id:
                syns = synonyms_by_node_id[ref_node_id]
            else:
                source_text = _node_source_text(node, sentence_text)
                node_pos = node.get("part_of_speech")
                source_key = f"{source_text.strip().lower()}|{str(node_pos or '').strip().lower()}"
                if source_key in synonyms_by_source_key:
                    syns = synonyms_by_source_key[source_key]
                else:
                    raw_syns = provider.get_synonyms(source_text, pos=node_pos, top_k=k)
                    syns = _postprocess_synonyms_for_node(node, raw_syns, source_text)
                    syns = syns[:k]
                    synonyms_by_source_key[source_key] = syns

            node["synonyms"] = list(syns)
            if isinstance(node_id, str):
                synonyms_by_node_id[node_id] = syns

            for child in node.get("linguistic_elements", []) or []:
                if isinstance(child, dict):
                    enrich_node(child)

        for child in sentence_node.get("linguistic_elements", []) or []:
            if isinstance(child, dict):
                enrich_node(child)


def _attach_cefr(
    doc: dict,
    predictor: Any,
    include_node_cefr: bool = True,
) -> None:
    for sentence_node in doc.values():
        if not isinstance(sentence_node, dict):
            continue

        sentence_text = str(sentence_node.get("content") or "")
        sentence_level = str(predictor.predict_level(sentence_node, sentence_text, sentence_text)).strip().upper()
        if sentence_level not in CEFR_ALLOWED_LEVELS:
            raise ValueError(f"Invalid CEFR level from predictor: {sentence_level!r}")
        sentence_node["cefr_level"] = sentence_level

        if not include_node_cefr:
            continue

        cefr_by_node_id: dict[str, str] = {}
        cefr_by_source_key: dict[str, str] = {}

        def enrich_node(node: dict) -> None:
            node_id = node.get("node_id")
            ref_node_id = node.get("ref_node_id")

            if isinstance(ref_node_id, str) and ref_node_id in cefr_by_node_id:
                level = cefr_by_node_id[ref_node_id]
            else:
                source_text = _node_source_text(node, sentence_text)
                pos = str(node.get("part_of_speech") or "").strip().lower()
                source_key = f"{source_text.strip().lower()}|{pos}"
                if source_key in cefr_by_source_key:
                    level = cefr_by_source_key[source_key]
                else:
                    level = str(predictor.predict_level(node, source_text, sentence_text)).strip().upper()
                    if level not in CEFR_ALLOWED_LEVELS:
                        raise ValueError(f"Invalid CEFR level from predictor: {level!r}")
                    cefr_by_source_key[source_key] = level

            node["cefr_level"] = level
            if isinstance(node_id, str):
                cefr_by_node_id[node_id] = level

            for child in node.get("linguistic_elements", []) or []:
                if isinstance(child, dict):
                    enrich_node(child)

        for child in sentence_node.get("linguistic_elements", []) or []:
            if isinstance(child, dict):
                enrich_node(child)


def _enforce_linguistic_elements_last(doc: dict) -> None:
    def reorder_node(node: dict) -> None:
        children = node.get("linguistic_elements", [])
        if isinstance(children, list):
            for child in children:
                if isinstance(child, dict):
                    reorder_node(child)
            value = node.pop("linguistic_elements")
            node["linguistic_elements"] = value

    for sentence_node in doc.values():
        if isinstance(sentence_node, dict):
            reorder_node(sentence_node)


def _resolve_translation_model_name(
    translation_model: str,
    local_model_dir: str = DEFAULT_LOCAL_TRANSLATION_MODEL_DIR,
) -> str:
    model_name = (translation_model or "").strip() or DEFAULT_TRANSLATION_MODEL
    if model_name == DEFAULT_TRANSLATION_MODEL and os.path.isdir(local_model_dir):
        return local_model_dir
    return model_name


def run_pipeline(
    text: str,
    model_dir: str | None = None,
    spacy_model: str = "en_core_web_sm",
    validation_mode: str = "v2_strict",
    note_mode: str = "template_only",
    backoff_debug_summary: bool = False,
    enable_translation: bool = False,
    translation_provider: str = "m2m100",
    translation_model: str = DEFAULT_TRANSLATION_MODEL,
    translation_source_lang: str = "en",
    translation_target_lang: str = "ru",
    translation_device: str = "auto",
    translate_nodes: bool = True,
    enable_phonetic: bool = False,
    phonetic_provider: str = "espeak",
    phonetic_binary: str = "auto",
    phonetic_nodes: bool = True,
    enable_synonyms: bool = False,
    synonyms_provider: str = "wordnet",
    synonyms_top_k: int = 5,
    synonym_nodes: bool = True,
    enable_cefr: bool = False,
    cefr_provider: str = "rule",
    cefr_model_path: str = DEFAULT_CEFR_MODEL_PATH,
    cefr_nodes: bool = True,
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

        resolved_translation_model = _resolve_translation_model_name(translation_model)
        translator = M2M100Translator(
            model_name=resolved_translation_model,
            device=translation_device,
        )
        _attach_translation(
            enriched,
            translator=translator,
            source_lang=translation_source_lang,
            target_lang=translation_target_lang,
            include_node_translations=translate_nodes,
        )

    if enable_phonetic:
        if phonetic_provider != "espeak":
            raise ValueError("phonetic_provider must be 'espeak'")
        from ela_pipeline.phonetic import EspeakPhoneticTranscriber

        transcriber = EspeakPhoneticTranscriber(binary=phonetic_binary)
        _attach_phonetic(
            enriched,
            transcriber=transcriber,
            include_node_phonetic=phonetic_nodes,
        )

    if enable_synonyms:
        if synonyms_provider != "wordnet":
            raise ValueError("synonyms_provider must be 'wordnet'")
        from ela_pipeline.synonyms import WordNetSynonymProvider

        provider = WordNetSynonymProvider()
        _attach_synonyms(
            enriched,
            provider=provider,
            top_k=synonyms_top_k,
            include_node_synonyms=synonym_nodes,
        )

    if enable_cefr:
        if cefr_provider == "rule":
            from ela_pipeline.cefr import RuleBasedCEFRPredictor

            predictor = RuleBasedCEFRPredictor()
        elif cefr_provider == "t5":
            from ela_pipeline.cefr import T5CEFRPredictor

            predictor = T5CEFRPredictor(model_path=cefr_model_path, device="cuda")
        else:
            raise ValueError("cefr_provider must be one of: rule | t5")

        _attach_cefr(
            enriched,
            predictor=predictor,
            include_node_cefr=cefr_nodes,
        )

    raise_if_invalid(validate_contract(enriched, validation_mode=validation_mode))
    raise_if_invalid(validate_frozen_structure(skeleton, enriched))
    _enforce_linguistic_elements_last(enriched)
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
        default=DEFAULT_TRANSLATION_MODEL,
        help=(
            "Hugging Face model id or local path for translation backend. "
            f"If omitted and `{DEFAULT_LOCAL_TRANSLATION_MODEL_DIR}` exists, it is used automatically."
        ),
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
    parser.add_argument("--phonetic", action="store_true", help="Enable phonetic transcription enrichment (UK/US).")
    parser.add_argument(
        "--phonetic-provider",
        default="espeak",
        choices=["espeak"],
        help="Phonetic backend provider (extensible).",
    )
    parser.add_argument(
        "--phonetic-binary",
        default="auto",
        choices=["auto", "espeak", "espeak-ng"],
        help="Binary resolver for phonetic backend.",
    )
    parser.add_argument(
        "--no-phonetic-nodes",
        action="store_true",
        help="Attach phonetic field to sentence only (skip phrase/word node phonetics).",
    )
    parser.add_argument("--synonyms", action="store_true", help="Enable synonym enrichment.")
    parser.add_argument(
        "--synonyms-provider",
        default="wordnet",
        choices=["wordnet"],
        help="Synonym backend provider (extensible).",
    )
    parser.add_argument(
        "--synonyms-top-k",
        type=int,
        default=5,
        help="Maximum synonyms per node (>=1).",
    )
    parser.add_argument(
        "--no-synonym-nodes",
        action="store_true",
        help="Attach synonyms to sentence only (skip phrase/word node synonyms).",
    )
    parser.add_argument("--cefr", action="store_true", help="Enable CEFR level enrichment.")
    parser.add_argument(
        "--cefr-provider",
        default="rule",
        choices=["rule", "t5"],
        help="CEFR backend provider.",
    )
    parser.add_argument(
        "--cefr-model-path",
        default=DEFAULT_CEFR_MODEL_PATH,
        help="Path to local T5 CEFR model directory for `--cefr-provider t5`.",
    )
    parser.add_argument(
        "--no-cefr-nodes",
        action="store_true",
        help="Attach CEFR level to sentence only (skip phrase/word node CEFR).",
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
        enable_phonetic=args.phonetic,
        phonetic_provider=args.phonetic_provider,
        phonetic_binary=args.phonetic_binary,
        phonetic_nodes=not args.no_phonetic_nodes,
        enable_synonyms=args.synonyms,
        synonyms_provider=args.synonyms_provider,
        synonyms_top_k=args.synonyms_top_k,
        synonym_nodes=not args.no_synonym_nodes,
        enable_cefr=args.cefr,
        cefr_provider=args.cefr_provider,
        cefr_model_path=args.cefr_model_path,
        cefr_nodes=not args.no_cefr_nodes,
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
