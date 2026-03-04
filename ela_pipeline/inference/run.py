"""Production inference runner: spaCy -> skeleton -> TAM -> local generator -> validator."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from typing import Any

from ela_pipeline.classifier.grammar_blueprints import build_note_blueprints
from ela_pipeline.classifier.grammar_rules import map_pedagogical_grammar_classes
from ela_pipeline.contract import deep_copy_contract
from ela_pipeline.parse.spacy_parser import load_nlp
from ela_pipeline.runtime import (
    decide_media_route,
    load_media_policy_limits_from_env,
    RuntimeFeatureRequest,
    build_runtime_capabilities,
    resolve_runtime_mode,
    validate_runtime_feature_request,
)
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
CEFR_LEVEL_ORDER = ("A1", "A2", "B1", "B2", "C1", "C2")
CEFR_LEVEL_TO_INDEX = {level: idx for idx, level in enumerate(CEFR_LEVEL_ORDER)}
LEGACY_NOTE_MODES = {"template_only", "llm", "hybrid", "two_stage"}
NOTE_MODE_CHOICES = tuple(sorted(LEGACY_NOTE_MODES | {"controlled"}))

WORD_POS_CEILING = {
    "article": "A1",
    "auxiliary verb": "A2",
    "determiner": "A2",
    "pronoun": "A2",
    "preposition": "B1",
    "conjunction": "B1",
    "particle": "B1",
}


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


def _cefr_clamp(level: str, *, low: str | None = None, high: str | None = None) -> str:
    idx = CEFR_LEVEL_TO_INDEX[level]
    if low is not None:
        idx = max(idx, CEFR_LEVEL_TO_INDEX[low])
    if high is not None:
        idx = min(idx, CEFR_LEVEL_TO_INDEX[high])
    return CEFR_LEVEL_ORDER[idx]


def _cefr_shift(level: str, delta: int) -> str:
    idx = CEFR_LEVEL_TO_INDEX[level] + delta
    idx = max(0, min(idx, len(CEFR_LEVEL_ORDER) - 1))
    return CEFR_LEVEL_ORDER[idx]


def _calibrate_cefr_level(
    node: dict,
    level: str,
    *,
    sentence_level: str,
    parent_level: str | None,
) -> str:
    node_type = str(node.get("type") or "").strip()
    pos = str(node.get("part_of_speech") or "").strip().lower()
    calibrated = level

    if node_type == "Phrase":
        calibrated = _cefr_clamp(calibrated, low=_cefr_shift(sentence_level, -1), high=_cefr_shift(sentence_level, 1))
    elif node_type == "Word":
        if pos in WORD_POS_CEILING:
            calibrated = _cefr_clamp(calibrated, high=WORD_POS_CEILING[pos])
        calibrated = _cefr_clamp(calibrated, high=_cefr_shift(sentence_level, 2))
        if parent_level is not None:
            calibrated = _cefr_clamp(calibrated, high=_cefr_shift(parent_level, 1))

    return calibrated


def _attach_translation(
    doc: dict,
    translator: Any,
    source_lang: str,
    target_lang: str,
    include_node_translations: bool = True,
    dual_channels: bool = False,
    translation_cache: Any | None = None,
    translation_cache_ttl_seconds: int = 86400,
) -> None:
    from ela_pipeline.translate import build_dual_translation_channels, build_translation_cache_key

    model_name = str(getattr(translator, "model_name", "unknown"))

    def translate_with_cache(source_text: str) -> str:
        if translation_cache is None:
            return translator.translate_text(source_text, source_lang=source_lang, target_lang=target_lang)

        cache_key = build_translation_cache_key(
            source_text=source_text,
            source_lang=source_lang,
            target_lang=target_lang,
            model_name=model_name,
        )
        cached = translation_cache.get(cache_key)
        if isinstance(cached, str) and cached:
            return cached
        translated = translator.translate_text(source_text, source_lang=source_lang, target_lang=target_lang)
        translation_cache.set(cache_key, translated, ttl_seconds=translation_cache_ttl_seconds)
        return translated

    def set_translation_map(
        node: dict[str, Any],
        *,
        text: str,
        include_model: bool,
    ) -> None:
        entry: dict[str, Any] = {
            "source_lang": source_lang,
            "target_lang": target_lang,
            "text": text,
        }
        if include_model:
            entry["model"] = getattr(translator, "model_name", "unknown")
        node["translations"] = {"backend_m2m100": entry}
        node["active_translation_provider"] = "backend_m2m100"

    for sentence_node in doc.values():
        if not isinstance(sentence_node, dict):
            continue

        sentence_text = str(sentence_node.get("content") or "")
        sentence_translation = translate_with_cache(sentence_text)
        if dual_channels:
            literary, idiomatic = build_dual_translation_channels(
                literary_text=sentence_translation,
                target_lang=target_lang,
            )
            sentence_node["translation_literary"] = {
                "source_lang": source_lang,
                "target_lang": target_lang,
                "model": getattr(translator, "model_name", "unknown"),
                "text": literary,
            }
            sentence_node["translation_idiomatic"] = {
                "source_lang": source_lang,
                "target_lang": target_lang,
                "text": idiomatic,
            }
            set_translation_map(
                sentence_node,
                text=literary,
                include_model=True,
            )
        else:
            set_translation_map(
                sentence_node,
                text=sentence_translation,
                include_model=True,
            )

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
                    translated = translate_with_cache(source_text)
                    translated_by_source_key[source_key] = translated

            if dual_channels:
                literary, idiomatic = build_dual_translation_channels(
                    literary_text=translated,
                    target_lang=target_lang,
                )
                node["translation_literary"] = {
                    "source_lang": source_lang,
                    "target_lang": target_lang,
                    "text": literary,
                }
                node["translation_idiomatic"] = {
                    "source_lang": source_lang,
                    "target_lang": target_lang,
                    "text": idiomatic,
                }
                set_translation_map(
                    node,
                    text=literary,
                    include_model=False,
                )
            else:
                set_translation_map(
                    node,
                    text=translated,
                    include_model=False,
                )
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
    def safe_transcribe(text: str, accent: str) -> str:
        source = str(text or "").strip()
        try:
            value = str(transcriber.transcribe_text(source, accent=accent) or "").strip()
        except Exception:
            value = ""
        # Contract validator requires non-empty uk/us when phonetic exists.
        return value if value else source

    for sentence_node in doc.values():
        if not isinstance(sentence_node, dict):
            continue

        sentence_text = str(sentence_node.get("content") or "")
        sentence_node["phonetic"] = {
            "uk": safe_transcribe(sentence_text, "uk"),
            "us": safe_transcribe(sentence_text, "us"),
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
                        "uk": safe_transcribe(source_text, "uk"),
                        "us": safe_transcribe(source_text, "us"),
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

        def enrich_node(node: dict, parent_level: str | None = sentence_level) -> None:
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
                    predicted_level = str(predictor.predict_level(node, source_text, sentence_text)).strip().upper()
                    if predicted_level not in CEFR_ALLOWED_LEVELS:
                        raise ValueError(f"Invalid CEFR level from predictor: {predicted_level!r}")
                    level = _calibrate_cefr_level(
                        node=node,
                        level=predicted_level,
                        sentence_level=sentence_level,
                        parent_level=parent_level,
                    )
                    cefr_by_source_key[source_key] = level

            node["cefr_level"] = level
            if isinstance(node_id, str):
                cefr_by_node_id[node_id] = level

            for child in node.get("linguistic_elements", []) or []:
                if isinstance(child, dict):
                    enrich_node(child, parent_level=level)

        for child in sentence_node.get("linguistic_elements", []) or []:
            if isinstance(child, dict):
                enrich_node(child)


def _attach_grammar_classes(doc: dict) -> None:
    def build_classes(node: dict) -> list[dict[str, Any]]:
        classes: list[dict[str, Any]] = []
        seen: set[str] = set()

        def add_class(class_id: str, confidence: float) -> None:
            cid = str(class_id or "").strip().lower()
            if not cid or cid in seen:
                return
            seen.add(cid)
            classes.append({"class_id": cid, "confidence": confidence})

        def collect_dep_labels(current: dict) -> list[str]:
            out: list[str] = []
            dep_label = str(current.get("dep_label") or "").strip().lower()
            if dep_label:
                out.append(dep_label)
            features = current.get("features") if isinstance(current.get("features"), dict) else {}
            if isinstance(features.get("dep"), list):
                out.extend(str(x).strip().lower() for x in features.get("dep", []) if str(x).strip())
            for child in current.get("linguistic_elements", []) or []:
                if isinstance(child, dict):
                    out.extend(collect_dep_labels(child))
            return out

        dep_signature = collect_dep_labels(node)
        mapped = map_pedagogical_grammar_classes(
            tense=node.get("tense"),
            aspect=node.get("aspect"),
            mood=node.get("mood"),
            voice=node.get("voice"),
            tam_construction=node.get("tam_construction"),
            dep_labels=dep_signature,
            content=node.get("content"),
            node_type=node.get("type"),
            part_of_speech=node.get("part_of_speech"),
        )
        for class_id in mapped:
            add_class(class_id, 0.9)

        return classes

    def walk(node: dict) -> None:
        node["grammar_classes"] = build_classes(node)
        for child in node.get("linguistic_elements", []) or []:
            if isinstance(child, dict):
                walk(child)

    for sentence_node in doc.values():
        if isinstance(sentence_node, dict):
            walk(sentence_node)


def _attach_generated_notes(doc: dict) -> None:
    def build_notes(node: dict) -> dict[str, str]:
        node_type = str(node.get("type") or "").strip().lower() or "node"
        role = str(node.get("grammatical_role") or "").strip().lower() or "unknown"
        tam = str(node.get("tam_construction") or "").strip().lower() or "none"
        cefr = str(node.get("cefr_level") or "").strip().upper() or "B1"
        content = str(node.get("content") or "").strip()

        class_ids = []
        for item in node.get("grammar_classes") or []:
            if isinstance(item, dict):
                class_id = str(item.get("class_id") or "").strip()
                if class_id:
                    class_ids.append(class_id)
        return build_note_blueprints(
            grammar_classes=class_ids,
            cefr_level=cefr,
            node_type=node_type,
            content=content,
            grammatical_role=role,
            tam_construction=tam,
        )

    def walk(node: dict) -> None:
        generated = build_notes(node)
        node["note_blueprints"] = dict(generated)
        node["generated_notes"] = generated
        existing_notes = node.get("linguistic_notes")
        if isinstance(existing_notes, list) and len(existing_notes) == 0:
            node["linguistic_notes"] = [generated["intermediate_text"]]
        for child in node.get("linguistic_elements", []) or []:
            if isinstance(child, dict):
                walk(child)

    for sentence_node in doc.values():
        if isinstance(sentence_node, dict):
            walk(sentence_node)


def _apply_controlled_notes(doc: dict) -> None:
    """Populate user-facing linguistic_notes from classifier-owned note blueprints."""

    def walk(node: dict) -> None:
        generated = node.get("generated_notes")
        if isinstance(generated, dict):
            preferred = str(generated.get("intermediate_text") or "").strip()
            fallback = str(generated.get("elementary_text") or "").strip()
            note = preferred or fallback
            node["linguistic_notes"] = [note] if note else []
        else:
            blueprints = node.get("note_blueprints")
            if isinstance(blueprints, dict):
                preferred = str(blueprints.get("intermediate_text") or "").strip()
                fallback = str(blueprints.get("elementary_text") or "").strip()
                note = preferred or fallback
                node["linguistic_notes"] = [note] if note else []
        for child in node.get("linguistic_elements", []) or []:
            if isinstance(child, dict):
                walk(child)

    for sentence_node in doc.values():
        if isinstance(sentence_node, dict):
            walk(sentence_node)


def _rewrite_controlled_notes_with_t5(doc: dict, renderer: Any) -> None:
    key_to_level = {
        "elementary_text": "elementary",
        "intermediate_text": "intermediate",
        "advanced_text": "advanced",
    }

    def walk(node: dict, sentence_text: str) -> None:
        generated = node.get("generated_notes")
        if isinstance(generated, dict):
            node.setdefault("note_blueprints", dict(generated))
            for key, level in key_to_level.items():
                blueprint = str(generated.get(key) or "").strip()
                if not blueprint:
                    continue
                rendered = str(
                    renderer.render_note(
                        blueprint_text=blueprint,
                        level=level,
                        sentence_text=sentence_text,
                        node_text=str(node.get("content") or "").strip(),
                        node_type=str(node.get("type") or "").strip(),
                        part_of_speech=str(node.get("part_of_speech") or "").strip(),
                        cefr_level=str(node.get("cefr_level") or "").strip(),
                    )
                    or ""
                ).strip()
                if rendered:
                    generated[key] = rendered
        for child in node.get("linguistic_elements", []) or []:
            if isinstance(child, dict):
                walk(child, sentence_text)

    for sentence_node in doc.values():
        if not isinstance(sentence_node, dict):
            continue
        sentence_text = str(sentence_node.get("content") or "")
        walk(sentence_node, sentence_text)


def _attach_classifier_profiles(
    doc: dict,
    classifier: Any,
    *,
    include_grammar_classes: bool = True,
    include_generated_notes: bool = True,
) -> None:
    def walk(node: dict, sentence_text: str) -> None:
        source_text = _node_source_text(node, sentence_text)
        profile = classifier.classify_node(node=node, source_text=source_text, sentence_text=sentence_text)
        node["cefr_level"] = str(profile.get("cefr_level") or "B1").strip().upper()
        if include_grammar_classes:
            grammar_classes = profile.get("grammar_classes")
            node["grammar_classes"] = grammar_classes if isinstance(grammar_classes, list) else []
        generated_notes = profile.get("generated_notes")
        if include_generated_notes and isinstance(generated_notes, dict):
            node["note_blueprints"] = dict(generated_notes)
            node["generated_notes"] = generated_notes
            existing_notes = node.get("linguistic_notes")
            if isinstance(existing_notes, list) and len(existing_notes) == 0:
                intermediate = str(generated_notes.get("intermediate_text") or "").strip()
                if intermediate:
                    node["linguistic_notes"] = [intermediate]
        for child in node.get("linguistic_elements", []) or []:
            if isinstance(child, dict):
                walk(child, sentence_text)

    for sentence_node in doc.values():
        if not isinstance(sentence_node, dict):
            continue
        sentence_text = str(sentence_node.get("content") or "")
        walk(sentence_node, sentence_text)


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


def _attach_note_generator_version(doc: dict, version: str) -> None:
    resolved = str(version or "").strip()
    if not resolved:
        return

    def walk(node: dict) -> None:
        node["note_generator_version"] = resolved
        for child in node.get("linguistic_elements", []) or []:
            if isinstance(child, dict):
                walk(child)

    for sentence_node in doc.values():
        if isinstance(sentence_node, dict):
            walk(sentence_node)


def _resolve_translation_model_name(
    translation_model: str,
    local_model_dir: str = DEFAULT_LOCAL_TRANSLATION_MODEL_DIR,
) -> str:
    model_name = (translation_model or "").strip() or DEFAULT_TRANSLATION_MODEL
    if model_name == DEFAULT_TRANSLATION_MODEL and os.path.isdir(local_model_dir):
        return local_model_dir
    return model_name


def _resolve_translation_cache_ttl_seconds(default_seconds: int = 86400) -> int:
    raw = os.getenv("ELA_TRANSLATION_CACHE_TTL_SECONDS", "").strip()
    if not raw:
        return default_seconds
    ttl = int(raw)
    if ttl <= 0:
        raise ValueError("ELA_TRANSLATION_CACHE_TTL_SECONDS must be > 0")
    return ttl


def run_pipeline(
    text: str,
    model_dir: str | None = None,
    spacy_model: str = "en_core_web_sm",
    validation_mode: str = "v2_strict",
    note_mode: str = "controlled",
    backoff_debug_summary: bool = False,
    enable_translation: bool = False,
    translation_provider: str = "m2m100",
    translation_model: str = DEFAULT_TRANSLATION_MODEL,
    translation_source_lang: str = "en",
    translation_target_lang: str = "ru",
    translation_device: str = "auto",
    translate_nodes: bool = True,
    translation_dual_channels: bool = False,
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
    enable_grammar_classes: bool = True,
    classifier_provider: str = "rule",
    classifier_model_path: str | None = None,
    classifier_device: str = "cuda",
) -> dict:
    nlp = load_nlp(spacy_model)

    skeleton = build_skeleton(text, nlp)
    _apply_strict_null_normalization(skeleton, validation_mode)
    raise_if_invalid(validate_contract(skeleton, validation_mode=validation_mode))

    enriched = deep_copy_contract(skeleton)
    apply_tam(enriched, nlp)
    _apply_strict_null_normalization(enriched, validation_mode)

    if model_dir and note_mode in LEGACY_NOTE_MODES:
        from ela_pipeline.annotate.local_generator import LocalT5Annotator

        annotator = LocalT5Annotator(
            model_dir=model_dir,
            note_mode=note_mode,
            backoff_debug_summary=backoff_debug_summary,
        )
        annotator.annotate(enriched)
        _attach_note_generator_version(
            enriched,
            version=f"local_t5::{note_mode}",
        )

    if enable_translation:
        if translation_provider != "m2m100":
            raise ValueError("translation_provider must be 'm2m100'")
        from ela_pipeline.translate import M2M100Translator, build_translation_cache_from_env

        resolved_translation_model = _resolve_translation_model_name(translation_model)
        translator = M2M100Translator(
            model_name=resolved_translation_model,
            device=translation_device,
        )
        translation_cache = build_translation_cache_from_env()
        translation_cache_ttl_seconds = _resolve_translation_cache_ttl_seconds()
        _attach_translation(
            enriched,
            translator=translator,
            source_lang=translation_source_lang,
            target_lang=translation_target_lang,
            include_node_translations=translate_nodes,
            dual_channels=translation_dual_channels,
            translation_cache=translation_cache,
            translation_cache_ttl_seconds=translation_cache_ttl_seconds,
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

    if classifier_provider == "deberta":
        from ela_pipeline.classifier.deberta import DebertaProfileClassifier

        classifier = DebertaProfileClassifier(
            model_path=classifier_model_path,
            device=classifier_device,
        )
        _attach_classifier_profiles(enriched, classifier=classifier)
    elif classifier_provider == "tabular":
        from ela_pipeline.classifier.tabular_cefr_predictor import TabularProfileClassifier

        classifier = TabularProfileClassifier(model_path=classifier_model_path)
        _attach_classifier_profiles(
            enriched,
            classifier=classifier,
            include_grammar_classes=False,
            include_generated_notes=False,
        )
    elif classifier_provider == "rule":
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

    if classifier_provider in {"rule", "tabular"} and enable_grammar_classes:
        _attach_grammar_classes(enriched)
        _attach_generated_notes(enriched)
    elif classifier_provider not in {"rule", "deberta", "tabular"}:
        raise ValueError("classifier_provider must be one of: rule | deberta | tabular")

    if note_mode == "controlled":
        _apply_controlled_notes(enriched)
        note_version = "controlled::classifier_blueprints"
        if model_dir:
            from ela_pipeline.annotate.controlled_renderer import ControlledT5NoteRenderer

            renderer = ControlledT5NoteRenderer(model_dir=model_dir)
            _rewrite_controlled_notes_with_t5(enriched, renderer=renderer)
            _apply_controlled_notes(enriched)
            note_version = "controlled_t5::blueprint_rewrite"
        _attach_note_generator_version(
            enriched,
            version=note_version,
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
        default="controlled",
        choices=NOTE_MODE_CHOICES,
        help=(
            "Inference mode: controlled (classifier blueprints -> user notes) "
            "or legacy T5 modes (template_only, llm, hybrid, two_stage)."
        ),
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
    parser.add_argument(
        "--translation-dual-channels",
        action="store_true",
        help="Emit both translation_literary and translation_idiomatic (keeps translation for compatibility).",
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
    parser.add_argument(
        "--classifier-provider",
        default="rule",
        choices=["rule", "deberta", "tabular"],
        help="Classifier profile provider (CEFR + grammar classes + generated note blueprints).",
    )
    parser.add_argument(
        "--classifier-model-path",
        default=None,
        help="Local model path for classifier_provider=deberta.",
    )
    parser.add_argument(
        "--classifier-device",
        default="cuda",
        choices=["cuda"],
        help="Device for classifier_provider=deberta.",
    )
    parser.add_argument(
        "--no-grammar-classes",
        action="store_true",
        help="Disable grammar_classes enrichment.",
    )
    parser.add_argument("--output", default=None)
    parser.add_argument("--media-duration-sec", type=int, default=None, help="Optional media duration for routing validation.")
    parser.add_argument("--media-size-bytes", type=int, default=None, help="Optional media size in bytes for routing validation.")
    parser.add_argument(
        "--runtime-mode",
        default="auto",
        choices=["auto", "offline", "online"],
        help="Runtime policy mode. `auto` resolves from ELA_RUNTIME_MODE (defaults to online).",
    )
    parser.add_argument(
        "--deployment-mode",
        default="auto",
        choices=["auto", "local", "backend", "distributed"],
        help="Deployment context for license-gated features. `auto` resolves from ELA_DEPLOYMENT_MODE.",
    )
    parser.add_argument("--persist-db", action="store_true", help="Persist inference result to PostgreSQL.")
    parser.add_argument(
        "--db-url",
        default=None,
        help="PostgreSQL DSN. If omitted, ELA_DATABASE_URL or DATABASE_URL env var is used.",
    )
    parser.add_argument("--db-run-id", default=None, help="Optional external run id for DB persistence.")
    parser.add_argument("--db-source-lang", default="en", help="Source language for sentence keying in DB.")
    parser.add_argument("--db-target-lang", default="none", help="Target language for sentence keying in DB.")
    args = parser.parse_args()

    runtime_mode = resolve_runtime_mode(args.runtime_mode)
    runtime_caps = build_runtime_capabilities(runtime_mode, deployment_mode=args.deployment_mode)
    validate_runtime_feature_request(
        runtime_caps,
        RuntimeFeatureRequest(
            enable_phonetic=bool(args.phonetic),
            enable_db_persistence=bool(args.persist_db),
        ),
    )

    if (args.media_duration_sec is None) != (args.media_size_bytes is None):
        raise ValueError("Both --media-duration-sec and --media-size-bytes must be provided together.")
    if args.media_duration_sec is not None and args.media_size_bytes is not None:
        limits = load_media_policy_limits_from_env()
        media_decision = decide_media_route(
            duration_seconds=args.media_duration_sec,
            size_bytes=args.media_size_bytes,
            limits=limits,
            runtime_caps=runtime_caps,
        )
        if media_decision.route == "reject":
            raise RuntimeError(media_decision.reason)
        print(f"Media routing: {media_decision.route} ({media_decision.reason})")

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
        translation_dual_channels=args.translation_dual_channels,
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
        enable_grammar_classes=not args.no_grammar_classes,
        classifier_provider=args.classifier_provider,
        classifier_model_path=args.classifier_model_path,
        classifier_device=args.classifier_device,
    )

    out_path = args.output
    if out_path is None:
        os.makedirs("inference_results", exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        out_path = os.path.join("inference_results", f"pipeline_result_{ts}.json")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    if args.persist_db:
        from ela_pipeline.db import persist_inference_result

        db_target_lang = args.translation_target_lang if args.translate else args.db_target_lang
        pipeline_context = {
            "runtime_mode": runtime_mode,
            "validation_mode": args.validation_mode,
            "note_mode": args.note_mode,
            "translate": bool(args.translate),
            "translation_provider": args.translation_provider if args.translate else "none",
            "translation_dual_channels": bool(args.translation_dual_channels) if args.translate else False,
            "phonetic": bool(args.phonetic),
            "phonetic_provider": args.phonetic_provider if args.phonetic else "none",
            "synonyms": bool(args.synonyms),
            "synonyms_provider": args.synonyms_provider if args.synonyms else "none",
            "cefr": bool(args.cefr),
            "cefr_provider": args.cefr_provider if args.cefr else "none",
            "schema_version": "v2",
        }
        mapping = persist_inference_result(
            result=result,
            db_url=args.db_url or "",
            source_lang=args.db_source_lang,
            target_lang=db_target_lang,
            pipeline_context=pipeline_context,
            run_id=args.db_run_id,
        )
        print(f"Persisted to DB: {len(mapping)} sentence(s)")

    print(f"Saved: {out_path}")


if __name__ == "__main__":
    main()
