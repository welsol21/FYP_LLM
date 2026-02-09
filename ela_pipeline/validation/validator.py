"""Contract validation for structure and content stability."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Set

from ela_pipeline.constants import NODE_TYPES, REQUIRED_NODE_FIELDS

NOTE_KINDS = {"semantic", "syntactic", "morphological", "discourse"}
NOTE_SOURCES = {"model", "rule", "fallback"}


@dataclass
class ValidationErrorItem:
    path: str
    message: str


@dataclass
class ValidationResult:
    ok: bool
    errors: List[ValidationErrorItem]


def _expect(condition: bool, errors: List[ValidationErrorItem], path: str, message: str) -> None:
    if not condition:
        errors.append(ValidationErrorItem(path=path, message=message))


def _validate_optional_source_span(node: Dict[str, Any], path: str, errors: List[ValidationErrorItem]) -> None:
    if "source_span" not in node:
        return
    span = node.get("source_span")
    _expect(isinstance(span, dict), errors, f"{path}.source_span", "source_span must be an object")
    if not isinstance(span, dict):
        return
    start = span.get("start")
    end = span.get("end")
    _expect(isinstance(start, int), errors, f"{path}.source_span.start", "start must be integer")
    _expect(isinstance(end, int), errors, f"{path}.source_span.end", "end must be integer")
    if isinstance(start, int) and isinstance(end, int):
        _expect(start >= 0, errors, f"{path}.source_span.start", "start must be >= 0")
        _expect(end >= start, errors, f"{path}.source_span.end", "end must be >= start")


def _validate_optional_grammatical_role(node: Dict[str, Any], path: str, errors: List[ValidationErrorItem]) -> None:
    if "grammatical_role" not in node:
        return
    _expect(
        isinstance(node.get("grammatical_role"), str),
        errors,
        f"{path}.grammatical_role",
        "grammatical_role must be string",
    )


def _validate_optional_dependency(node: Dict[str, Any], path: str, errors: List[ValidationErrorItem]) -> None:
    if "dep_label" in node:
        _expect(
            isinstance(node.get("dep_label"), str),
            errors,
            f"{path}.dep_label",
            "dep_label must be string",
        )
    if "head_id" in node:
        head_id = node.get("head_id")
        _expect(
            head_id is None or isinstance(head_id, str),
            errors,
            f"{path}.head_id",
            "head_id must be string or null",
        )
        if isinstance(head_id, str) and isinstance(node.get("node_id"), str):
            _expect(head_id != node.get("node_id"), errors, f"{path}.head_id", "head_id must not equal node_id")


def _validate_optional_verbal_fields(node: Dict[str, Any], path: str, errors: List[ValidationErrorItem]) -> None:
    for field in ("aspect", "mood", "voice", "finiteness"):
        if field in node:
            _expect(
                isinstance(node.get(field), str),
                errors,
                f"{path}.{field}",
                f"{field} must be string",
            )


def _validate_optional_features(node: Dict[str, Any], path: str, errors: List[ValidationErrorItem]) -> None:
    if "features" not in node:
        return
    features = node.get("features")
    _expect(isinstance(features, dict), errors, f"{path}.features", "features must be object")
    if not isinstance(features, dict):
        return
    for key, value in features.items():
        _expect(isinstance(key, str), errors, f"{path}.features", "feature keys must be string")
        _expect(isinstance(value, str), errors, f"{path}.features.{key}", "feature values must be string")


def _validate_optional_notes(node: Dict[str, Any], path: str, errors: List[ValidationErrorItem]) -> None:
    if "notes" not in node:
        return
    notes = node.get("notes")
    _expect(isinstance(notes, list), errors, f"{path}.notes", "notes must be list")
    if not isinstance(notes, list):
        return
    for idx, note in enumerate(notes):
        item_path = f"{path}.notes[{idx}]"
        _expect(isinstance(note, dict), errors, item_path, "note item must be object")
        if not isinstance(note, dict):
            continue
        _expect(isinstance(note.get("text"), str), errors, f"{item_path}.text", "text must be string")
        _expect(note.get("kind") in NOTE_KINDS, errors, f"{item_path}.kind", "kind must be one of semantic|syntactic|morphological|discourse")
        confidence = note.get("confidence")
        _expect(
            isinstance(confidence, (float, int)),
            errors,
            f"{item_path}.confidence",
            "confidence must be number",
        )
        if isinstance(confidence, (float, int)):
            _expect(
                0.0 <= float(confidence) <= 1.0,
                errors,
                f"{item_path}.confidence",
                "confidence must be in range [0, 1]",
            )
        _expect(note.get("source") in NOTE_SOURCES, errors, f"{item_path}.source", "source must be one of model|rule|fallback")


def _validate_optional_ids(
    node: Dict[str, Any],
    path: str,
    errors: List[ValidationErrorItem],
    seen_ids: Set[str],
    expected_parent_id: str | None,
) -> None:
    if "node_id" in node:
        node_id = node.get("node_id")
        _expect(isinstance(node_id, str), errors, f"{path}.node_id", "node_id must be string")
        if isinstance(node_id, str):
            _expect(node_id not in seen_ids, errors, f"{path}.node_id", "node_id must be unique")
            seen_ids.add(node_id)
    if "parent_id" in node:
        parent_id = node.get("parent_id")
        _expect(
            parent_id is None or isinstance(parent_id, str),
            errors,
            f"{path}.parent_id",
            "parent_id must be string or null",
        )
        if expected_parent_id is None:
            _expect(parent_id is None, errors, f"{path}.parent_id", "Sentence parent_id must be null")
        else:
            _expect(parent_id == expected_parent_id, errors, f"{path}.parent_id", "parent_id mismatch")


def _validate_node(
    node: Dict[str, Any],
    path: str,
    errors: List[ValidationErrorItem],
    seen_ids: Set[str],
    expected_parent_id: str | None = None,
) -> None:
    _expect(isinstance(node, dict), errors, path, "Node must be an object")
    if not isinstance(node, dict):
        return

    missing = REQUIRED_NODE_FIELDS - set(node.keys())
    _expect(not missing, errors, path, f"Missing required fields: {sorted(missing)}")

    node_type = node.get("type")
    _expect(node_type in NODE_TYPES, errors, f"{path}.type", "Invalid node type")

    _expect(isinstance(node.get("content"), str), errors, f"{path}.content", "content must be string")
    _expect(isinstance(node.get("tense"), str), errors, f"{path}.tense", "tense must be string")
    _expect(isinstance(node.get("part_of_speech"), str), errors, f"{path}.part_of_speech", "part_of_speech must be string")
    _validate_optional_source_span(node, path, errors)
    _validate_optional_grammatical_role(node, path, errors)
    _validate_optional_dependency(node, path, errors)
    _validate_optional_verbal_fields(node, path, errors)
    _validate_optional_features(node, path, errors)
    _validate_optional_notes(node, path, errors)
    _validate_optional_ids(node, path, errors, seen_ids, expected_parent_id)

    notes = node.get("linguistic_notes")
    _expect(isinstance(notes, list), errors, f"{path}.linguistic_notes", "linguistic_notes must be list")
    if isinstance(notes, list):
        for idx, note in enumerate(notes):
            _expect(isinstance(note, str), errors, f"{path}.linguistic_notes[{idx}]", "note must be string")

    children = node.get("linguistic_elements")
    _expect(isinstance(children, list), errors, f"{path}.linguistic_elements", "linguistic_elements must be list")
    if not isinstance(children, list):
        return

    for idx, child in enumerate(children):
        child_path = f"{path}.linguistic_elements[{idx}]"
        _validate_node(child, child_path, errors, seen_ids, expected_parent_id=node.get("node_id"))

    if node_type == "Sentence":
        for idx, child in enumerate(children):
            _expect(child.get("type") == "Phrase", errors, f"{path}.linguistic_elements[{idx}].type", "Sentence can only contain Phrase")
    if node_type == "Phrase":
        for idx, child in enumerate(children):
            _expect(child.get("type") == "Word", errors, f"{path}.linguistic_elements[{idx}].type", "Phrase can only contain Word")
        _expect(
            len(children) >= 2,
            errors,
            f"{path}.linguistic_elements",
            "Phrase must contain at least 2 Word nodes",
        )


def validate_contract(doc: Dict[str, Any]) -> ValidationResult:
    errors: List[ValidationErrorItem] = []
    seen_ids: Set[str] = set()
    _expect(isinstance(doc, dict), errors, "$", "Top-level must be an object keyed by sentence content")

    if isinstance(doc, dict):
        for sentence_key, sentence_node in doc.items():
            _expect(isinstance(sentence_key, str), errors, "$", "Top-level keys must be strings")
            _validate_node(sentence_node, f"$.{sentence_key}", errors, seen_ids, expected_parent_id=None)
            if isinstance(sentence_node, dict):
                _expect(sentence_node.get("type") == "Sentence", errors, f"$.{sentence_key}.type", "Top-level value must be Sentence")
                _expect(sentence_node.get("content") == sentence_key, errors, f"$.{sentence_key}.content", "Sentence content must match top-level key")

    return ValidationResult(ok=not errors, errors=errors)


def _freeze_compare(base: Dict[str, Any], candidate: Dict[str, Any], path: str, errors: List[ValidationErrorItem]) -> None:
    for field in (
        "type",
        "content",
        "part_of_speech",
        "node_id",
        "parent_id",
        "source_span",
        "grammatical_role",
        "dep_label",
        "head_id",
        "features",
    ):
        if base.get(field) != candidate.get(field):
            errors.append(ValidationErrorItem(path=f"{path}.{field}", message="Frozen field mismatch"))

    base_children = base.get("linguistic_elements", [])
    cand_children = candidate.get("linguistic_elements", [])
    if len(base_children) != len(cand_children):
        errors.append(ValidationErrorItem(path=f"{path}.linguistic_elements", message="Children count mismatch"))
        return

    for idx, (base_child, cand_child) in enumerate(zip(base_children, cand_children)):
        _freeze_compare(base_child, cand_child, f"{path}.linguistic_elements[{idx}]", errors)


def validate_frozen_structure(skeleton: Dict[str, Any], enriched: Dict[str, Any]) -> ValidationResult:
    errors: List[ValidationErrorItem] = []

    if set(skeleton.keys()) != set(enriched.keys()):
        errors.append(ValidationErrorItem(path="$", message="Top-level sentence keys mismatch"))
        return ValidationResult(ok=False, errors=errors)

    for key in skeleton.keys():
        _freeze_compare(skeleton[key], enriched[key], f"$.{key}", errors)

    return ValidationResult(ok=not errors, errors=errors)


def raise_if_invalid(result: ValidationResult) -> None:
    if result.ok:
        return
    details = "\n".join(f"- {e.path}: {e.message}" for e in result.errors)
    raise ValueError(f"Validation failed:\n{details}")
