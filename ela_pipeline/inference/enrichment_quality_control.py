"""Aggregate quality checks for optional enrichment fields in inference contract."""

from __future__ import annotations

from typing import Any, Dict, Iterable

from ela_pipeline.inference.run import CEFR_ALLOWED_LEVELS


def _walk_nodes(node: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    yield node
    for child in node.get("linguistic_elements", []) or []:
        if isinstance(child, dict):
            yield from _walk_nodes(child)


def _is_valid_translation(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and isinstance(value.get("source_lang"), str)
        and value.get("source_lang", "").strip() != ""
        and isinstance(value.get("target_lang"), str)
        and value.get("target_lang", "").strip() != ""
        and isinstance(value.get("text"), str)
        and value.get("text", "").strip() != ""
    )


def _is_valid_phonetic(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and isinstance(value.get("uk"), str)
        and value.get("uk", "").strip() != ""
        and isinstance(value.get("us"), str)
        and value.get("us", "").strip() != ""
    )


def _is_valid_synonyms(value: Any) -> bool:
    if not isinstance(value, list) or not value:
        return False
    normalized = []
    for item in value:
        if not isinstance(item, str) or item.strip() == "":
            return False
        normalized.append(item.strip().lower())
    return len(set(normalized)) == len(normalized)


def _is_valid_cefr(value: Any) -> bool:
    return isinstance(value, str) and value.strip().upper() in CEFR_ALLOWED_LEVELS


def _field_stats(nodes: list[Dict[str, Any]], field: str, validator) -> Dict[str, Any]:
    valid = 0
    missing = 0
    invalid = 0
    for node in nodes:
        if field not in node:
            missing += 1
            continue
        if validator(node.get(field)):
            valid += 1
        else:
            invalid += 1
    total = len(nodes)
    return {
        "valid": valid,
        "missing": missing,
        "invalid": invalid,
        "coverage": round(valid / total, 6) if total else 0.0,
    }


def _extract_enrichment_probe_stats(result: Dict[str, Any]) -> Dict[str, Any]:
    root = next(iter(result.values()))
    nodes = list(_walk_nodes(root))
    non_sentence_nodes = [n for n in nodes if str(n.get("type") or "").strip() != "Sentence"]

    return {
        "nodes": len(nodes),
        "non_sentence_nodes": len(non_sentence_nodes),
        "sentence": {
            "translation_ok": _is_valid_translation(root.get("translation")),
            "phonetic_ok": _is_valid_phonetic(root.get("phonetic")),
            "synonyms_ok": _is_valid_synonyms(root.get("synonyms")),
            "cefr_ok": _is_valid_cefr(root.get("cefr_level")),
        },
        "node_fields": {
            "translation": _field_stats(non_sentence_nodes, "translation", _is_valid_translation),
            "phonetic": _field_stats(non_sentence_nodes, "phonetic", _is_valid_phonetic),
            "synonyms": _field_stats(non_sentence_nodes, "synonyms", _is_valid_synonyms),
            "cefr_level": _field_stats(non_sentence_nodes, "cefr_level", _is_valid_cefr),
        },
    }
