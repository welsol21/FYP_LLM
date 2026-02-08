"""Structural validation entrypoints."""

from __future__ import annotations

from typing import Any, Dict

from ela_pipeline.validation.validator import ValidationResult, validate_contract


def validate_schema(doc: Dict[str, Any]) -> ValidationResult:
    """Validate structure against the contract shape from docs/sample.json."""
    return validate_contract(doc)
