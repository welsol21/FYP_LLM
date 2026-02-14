"""Contract validation for structure and content stability."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Set

from ela_pipeline.constants import NODE_TYPES, REQUIRED_NODE_FIELDS

NOTE_KINDS = {"semantic", "syntactic", "morphological", "discourse"}
NOTE_SOURCES = {"model", "rule", "fallback"}
VALIDATION_MODES = {"v1", "v2_strict"}
STRICT_V2_REQUIRED_FIELDS = {"node_id", "source_span", "grammatical_role", "schema_version"}
TAM_FIELDS = ("tense", "aspect", "mood", "voice", "finiteness")


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


def _validate_tam_field(
    node: Dict[str, Any],
    field: str,
    path: str,
    errors: List[ValidationErrorItem],
    validation_mode: str,
) -> None:
    value = node.get(field)
    if validation_mode == "v2_strict":
        _expect(
            value is None or isinstance(value, str),
            errors,
            f"{path}.{field}",
            f"{field} must be string or null in strict mode",
        )
        if isinstance(value, str):
            _expect(
                value.lower() != "null",
                errors,
                f"{path}.{field}",
                f"{field} must use real null, not string 'null', in strict mode",
            )
        return
    _expect(
        isinstance(value, str),
        errors,
        f"{path}.{field}",
        f"{field} must be string",
    )


def _validate_optional_verbal_fields(
    node: Dict[str, Any],
    path: str,
    errors: List[ValidationErrorItem],
    validation_mode: str,
) -> None:
    for field in ("aspect", "mood", "voice", "finiteness"):
        if field in node:
            _validate_tam_field(node, field, path, errors, validation_mode)
    if "tam_construction" in node:
        value = node.get("tam_construction")
        _expect(isinstance(value, str), errors, f"{path}.tam_construction", "tam_construction must be string")
        if isinstance(value, str):
            _expect(
                value.strip() != "",
                errors,
                f"{path}.tam_construction",
                "tam_construction must be non-empty string",
            )


def _validate_modal_perfect_policy(
    node: Dict[str, Any],
    path: str,
    errors: List[ValidationErrorItem],
    validation_mode: str,
) -> None:
    if validation_mode != "v2_strict":
        return
    construction = node.get("tam_construction")
    if construction == "modal_perfect":
        _expect(node.get("mood") == "modal", errors, f"{path}.mood", "modal_perfect requires mood='modal'")
        _expect(node.get("aspect") == "perfect", errors, f"{path}.aspect", "modal_perfect requires aspect='perfect'")
        _expect(node.get("tense") is None, errors, f"{path}.tense", "modal_perfect requires tense=null in strict mode")
    if node.get("mood") == "modal" and node.get("aspect") == "perfect" and node.get("tense") is None:
        _expect(
            node.get("tam_construction") == "modal_perfect",
            errors,
            f"{path}.tam_construction",
            "modal mood + perfect aspect + tense null requires tam_construction='modal_perfect' in strict mode",
        )


def _validate_optional_features(
    node: Dict[str, Any],
    path: str,
    errors: List[ValidationErrorItem],
    validation_mode: str,
) -> None:
    if "features" not in node:
        return
    features = node.get("features")
    _expect(isinstance(features, dict), errors, f"{path}.features", "features must be object")
    if not isinstance(features, dict):
        return
    for key, value in features.items():
        _expect(isinstance(key, str), errors, f"{path}.features", "feature keys must be string")
        if validation_mode == "v2_strict":
            _expect(
                value is None or isinstance(value, str),
                errors,
                f"{path}.features.{key}",
                "feature values must be string or null in strict mode",
            )
            if isinstance(value, str):
                _expect(
                    value.lower() != "null",
                    errors,
                    f"{path}.features.{key}",
                    "feature values must use real null, not string 'null', in strict mode",
                )
        else:
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


def _validate_optional_trace_fields(node: Dict[str, Any], path: str, errors: List[ValidationErrorItem]) -> None:
    for field in ("quality_flags", "rejected_candidates", "reason_codes"):
        if field not in node:
            continue
        value = node.get(field)
        _expect(isinstance(value, list), errors, f"{path}.{field}", f"{field} must be list")
        if not isinstance(value, list):
            continue
        for idx, item in enumerate(value):
            _expect(
                isinstance(item, str),
                errors,
                f"{path}.{field}[{idx}]",
                f"{field} items must be string",
            )


def _is_tam_relevant_node(node: Dict[str, Any]) -> bool:
    node_type = str(node.get("type") or "").strip().lower()
    pos = str(node.get("part_of_speech") or "").strip().lower()
    tam_construction = str(node.get("tam_construction") or "").strip().lower()
    if node_type == "sentence":
        return True
    if pos in {"verb phrase", "clause", "verb", "auxiliary verb"}:
        return True
    return tam_construction not in {"", "none", "null"}


def _validate_optional_template_selection(node: Dict[str, Any], path: str, errors: List[ValidationErrorItem]) -> None:
    if "template_selection" not in node:
        return
    selection = node.get("template_selection")
    _expect(isinstance(selection, dict), errors, f"{path}.template_selection", "template_selection must be object")
    if not isinstance(selection, dict):
        return

    for key in (
        "level",
        "template_id",
        "matched_key",
        "registry_version",
        "context_key_l1",
        "context_key_l2",
        "context_key_l3",
        "context_key_matched",
        "selection_mode",
    ):
        if key in selection:
            value = selection.get(key)
            _expect(
                value is None or isinstance(value, str),
                errors,
                f"{path}.template_selection.{key}",
                f"{key} must be string or null",
            )

    reason = selection.get("matched_level_reason")
    if reason is not None:
        _expect(
            isinstance(reason, str),
            errors,
            f"{path}.template_selection.matched_level_reason",
            "matched_level_reason must be string",
        )
        level = str(selection.get("level") or "").upper()
        if isinstance(reason, str) and reason == "tam_dropped":
            _expect(
                level == "L2_DROP_TAM",
                errors,
                f"{path}.template_selection.level",
                "matched_level_reason='tam_dropped' requires level='L2_DROP_TAM'",
            )
            _expect(
                _is_tam_relevant_node(node),
                errors,
                f"{path}.template_selection.matched_level_reason",
                "matched_level_reason='tam_dropped' is only allowed for TAM-relevant nodes",
            )

    level = str(selection.get("level") or "").upper()
    quality_flags = node.get("quality_flags")
    if isinstance(quality_flags, list):
        has_backoff = "backoff_used" in quality_flags
        is_backoff_level = bool(level and level != "L1_EXACT")
        if is_backoff_level:
            _expect(
                has_backoff,
                errors,
                f"{path}.quality_flags",
                "backoff_used is required when template_selection.level is not L1_EXACT",
            )
        elif level == "L1_EXACT":
            _expect(
                not has_backoff,
                errors,
                f"{path}.quality_flags",
                "backoff_used is not allowed when template_selection.level is L1_EXACT",
            )


def _validate_optional_backoff_summary(node: Dict[str, Any], path: str, errors: List[ValidationErrorItem]) -> None:
    if "backoff_nodes_count" in node:
        count = node.get("backoff_nodes_count")
        _expect(isinstance(count, int), errors, f"{path}.backoff_nodes_count", "backoff_nodes_count must be integer")
        if isinstance(count, int):
            _expect(count >= 0, errors, f"{path}.backoff_nodes_count", "backoff_nodes_count must be >= 0")
    if "backoff_leaf_nodes_count" in node:
        count = node.get("backoff_leaf_nodes_count")
        _expect(
            isinstance(count, int),
            errors,
            f"{path}.backoff_leaf_nodes_count",
            "backoff_leaf_nodes_count must be integer",
        )
        if isinstance(count, int):
            _expect(
                count >= 0,
                errors,
                f"{path}.backoff_leaf_nodes_count",
                "backoff_leaf_nodes_count must be >= 0",
            )
    if "backoff_unique_spans_count" in node:
        count = node.get("backoff_unique_spans_count")
        _expect(
            isinstance(count, int),
            errors,
            f"{path}.backoff_unique_spans_count",
            "backoff_unique_spans_count must be integer",
        )
        if isinstance(count, int):
            _expect(
                count >= 0,
                errors,
                f"{path}.backoff_unique_spans_count",
                "backoff_unique_spans_count must be >= 0",
            )

    if "backoff_summary" not in node:
        return

    summary = node.get("backoff_summary")
    _expect(isinstance(summary, dict), errors, f"{path}.backoff_summary", "backoff_summary must be object")
    if not isinstance(summary, dict):
        return

    nodes = summary.get("nodes")
    _expect(isinstance(nodes, list), errors, f"{path}.backoff_summary.nodes", "nodes must be list")
    if isinstance(nodes, list):
        for idx, item in enumerate(nodes):
            _expect(
                isinstance(item, str),
                errors,
                f"{path}.backoff_summary.nodes[{idx}]",
                "node id must be string",
            )

    leaf_nodes = summary.get("leaf_nodes")
    if leaf_nodes is not None:
        _expect(isinstance(leaf_nodes, list), errors, f"{path}.backoff_summary.leaf_nodes", "leaf_nodes must be list")
        if isinstance(leaf_nodes, list):
            for idx, item in enumerate(leaf_nodes):
                _expect(
                    isinstance(item, str),
                    errors,
                    f"{path}.backoff_summary.leaf_nodes[{idx}]",
                    "node id must be string",
                )

    unique_spans = summary.get("unique_spans")
    if unique_spans is not None:
        _expect(
            isinstance(unique_spans, list),
            errors,
            f"{path}.backoff_summary.unique_spans",
            "unique_spans must be list",
        )
        if isinstance(unique_spans, list):
            for idx, item in enumerate(unique_spans):
                _expect(
                    isinstance(item, str),
                    errors,
                    f"{path}.backoff_summary.unique_spans[{idx}]",
                    "span key must be string",
                )

    reasons = summary.get("reasons")
    _expect(isinstance(reasons, list), errors, f"{path}.backoff_summary.reasons", "reasons must be list")
    if isinstance(reasons, list):
        for idx, item in enumerate(reasons):
            _expect(
                isinstance(item, str),
                errors,
                f"{path}.backoff_summary.reasons[{idx}]",
                "reason must be string",
            )


def _validate_optional_rejected_candidate_stats(
    node: Dict[str, Any],
    path: str,
    errors: List[ValidationErrorItem],
) -> None:
    if "rejected_candidate_stats" not in node:
        return
    stats = node.get("rejected_candidate_stats")
    _expect(
        isinstance(stats, list),
        errors,
        f"{path}.rejected_candidate_stats",
        "rejected_candidate_stats must be list",
    )
    if not isinstance(stats, list):
        return
    for idx, item in enumerate(stats):
        item_path = f"{path}.rejected_candidate_stats[{idx}]"
        _expect(isinstance(item, dict), errors, item_path, "stats item must be object")
        if not isinstance(item, dict):
            continue
        _expect(isinstance(item.get("text"), str), errors, f"{item_path}.text", "text must be string")
        count = item.get("count")
        _expect(isinstance(count, int), errors, f"{item_path}.count", "count must be integer")
        if isinstance(count, int):
            _expect(count >= 1, errors, f"{item_path}.count", "count must be >= 1")
        reasons = item.get("reasons")
        _expect(isinstance(reasons, list), errors, f"{item_path}.reasons", "reasons must be list")
        if isinstance(reasons, list):
            for reason_idx, reason in enumerate(reasons):
                _expect(
                    isinstance(reason, str),
                    errors,
                    f"{item_path}.reasons[{reason_idx}]",
                    "reason must be string",
                )


def _validate_optional_schema_version(node: Dict[str, Any], path: str, errors: List[ValidationErrorItem]) -> None:
    if "schema_version" not in node:
        return
    schema_version = node.get("schema_version")
    _expect(
        isinstance(schema_version, str),
        errors,
        f"{path}.schema_version",
        "schema_version must be string",
    )
    if isinstance(schema_version, str):
        _expect(
            schema_version.strip() != "",
            errors,
            f"{path}.schema_version",
            "schema_version must be non-empty",
        )


def _validate_required_fields(
    node: Dict[str, Any],
    path: str,
    errors: List[ValidationErrorItem],
    validation_mode: str,
) -> None:
    required_fields = set(REQUIRED_NODE_FIELDS)
    if validation_mode == "v2_strict":
        required_fields |= STRICT_V2_REQUIRED_FIELDS
    missing = required_fields - set(node.keys())
    _expect(not missing, errors, path, f"Missing required fields: {sorted(missing)}")


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
    validation_mode: str,
    expected_parent_id: str | None = None,
) -> None:
    _expect(isinstance(node, dict), errors, path, "Node must be an object")
    if not isinstance(node, dict):
        return

    _validate_required_fields(node, path, errors, validation_mode)

    node_type = node.get("type")
    _expect(node_type in NODE_TYPES, errors, f"{path}.type", "Invalid node type")

    _expect(isinstance(node.get("content"), str), errors, f"{path}.content", "content must be string")
    _validate_tam_field(node, "tense", path, errors, validation_mode)
    _expect(isinstance(node.get("part_of_speech"), str), errors, f"{path}.part_of_speech", "part_of_speech must be string")
    _validate_optional_source_span(node, path, errors)
    _validate_optional_grammatical_role(node, path, errors)
    _validate_optional_dependency(node, path, errors)
    _validate_optional_verbal_fields(node, path, errors, validation_mode)
    _validate_modal_perfect_policy(node, path, errors, validation_mode)
    _validate_optional_features(node, path, errors, validation_mode)
    _validate_optional_notes(node, path, errors)
    _validate_optional_trace_fields(node, path, errors)
    _validate_optional_template_selection(node, path, errors)
    _validate_optional_backoff_summary(node, path, errors)
    _validate_optional_rejected_candidate_stats(node, path, errors)
    _validate_optional_schema_version(node, path, errors)
    if validation_mode == "v2_strict":
        _expect(node.get("schema_version") == "v2", errors, f"{path}.schema_version", "schema_version must be 'v2' in strict mode")
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
        _validate_node(
            child,
            child_path,
            errors,
            seen_ids,
            validation_mode=validation_mode,
            expected_parent_id=node.get("node_id"),
        )

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


def validate_contract(doc: Dict[str, Any], validation_mode: str = "v2_strict") -> ValidationResult:
    errors: List[ValidationErrorItem] = []
    seen_ids: Set[str] = set()
    _expect(validation_mode in VALIDATION_MODES, errors, "$.validation_mode", "validation_mode must be v1 or v2_strict")
    _expect(isinstance(doc, dict), errors, "$", "Top-level must be an object keyed by sentence content")

    if isinstance(doc, dict):
        for sentence_key, sentence_node in doc.items():
            _expect(isinstance(sentence_key, str), errors, "$", "Top-level keys must be strings")
            _validate_node(
                sentence_node,
                f"$.{sentence_key}",
                errors,
                seen_ids,
                validation_mode=validation_mode,
                expected_parent_id=None,
            )
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
        "schema_version",
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
