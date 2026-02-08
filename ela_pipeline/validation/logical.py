"""Logical/frozen validation entrypoints."""

from __future__ import annotations

from typing import Any, Dict

from ela_pipeline.validation.validator import ValidationResult, validate_frozen_structure


def validate_logical_frozen(skeleton: Dict[str, Any], enriched: Dict[str, Any]) -> ValidationResult:
    """Validate that enriched content did not alter frozen fields/content."""
    return validate_frozen_structure(skeleton, enriched)
