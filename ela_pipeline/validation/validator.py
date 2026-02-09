"""Contract validation for structure and content stability."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from ela_pipeline.constants import NODE_TYPES, REQUIRED_NODE_FIELDS


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


def _validate_node(node: Dict[str, Any], path: str, errors: List[ValidationErrorItem]) -> None:
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
        _validate_node(child, child_path, errors)

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
    _expect(isinstance(doc, dict), errors, "$", "Top-level must be an object keyed by sentence content")

    if isinstance(doc, dict):
        for sentence_key, sentence_node in doc.items():
            _expect(isinstance(sentence_key, str), errors, "$", "Top-level keys must be strings")
            _validate_node(sentence_node, f"$.{sentence_key}", errors)
            if isinstance(sentence_node, dict):
                _expect(sentence_node.get("type") == "Sentence", errors, f"$.{sentence_key}.type", "Top-level value must be Sentence")
                _expect(sentence_node.get("content") == sentence_key, errors, f"$.{sentence_key}.content", "Sentence content must match top-level key")

    return ValidationResult(ok=not errors, errors=errors)


def _freeze_compare(base: Dict[str, Any], candidate: Dict[str, Any], path: str, errors: List[ValidationErrorItem]) -> None:
    for field in ("type", "content", "part_of_speech"):
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
