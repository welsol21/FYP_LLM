"""Runtime wrapper for tabular CEFR baseline models."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import joblib

from .curriculum import validate_per_class_cefr_ladder
from .train_tabular_cefr_baseline import extract_tabular_features

CEFR_ALLOWED = {"A1", "A2", "B1", "B2", "C1", "C2"}


def _normalize_cefr(label: Any) -> str:
    value = str(label or "").strip().upper()
    if value in CEFR_ALLOWED:
        return value
    raise ValueError(f"Invalid CEFR label from tabular classifier: {label!r}")


class TabularCefrPredictor:
    def __init__(self, model: Any) -> None:
        self._model = model

    @classmethod
    def from_path(cls, model_path: str) -> "TabularCefrPredictor":
        path = Path(model_path)
        if not path.is_file():
            raise FileNotFoundError(f"tabular CEFR model not found: {model_path}")
        return cls(joblib.load(path))

    def predict_row(self, row: dict[str, Any]) -> str:
        features = extract_tabular_features(row)
        result = self._model.predict([features])
        if not result:
            return ""
        return str(result[0]).strip().upper()

    def predict_rows(self, rows: list[dict[str, Any]]) -> list[str]:
        feature_rows = [extract_tabular_features(row) for row in rows]
        out = self._model.predict(feature_rows)
        return [str(item).strip().upper() for item in out]


class TabularProfileClassifier:
    """CEFR classifier backed by the tabular baseline plus runtime metadata."""

    def __init__(self, model_path: str | None) -> None:
        path = Path(str(model_path or "").strip())
        if not str(path):
            raise ValueError("classifier_model_path must be provided for classifier_provider=tabular")
        if path.is_dir():
            model_file = path / "best_tabular_cefr_baseline.joblib"
            metadata_file = path / "classifier_metadata.json"
        else:
            model_file = path
            metadata_file = path.parent / "classifier_metadata.json"
        if not model_file.is_file():
            raise FileNotFoundError(f"tabular classifier model not found: {model_file}")
        if not metadata_file.is_file():
            raise FileNotFoundError(f"Missing classifier metadata file: {metadata_file}")

        self._predictor = TabularCefrPredictor.from_path(str(model_file))
        with metadata_file.open("r", encoding="utf-8") as f:
            metadata = json.load(f)
        if not isinstance(metadata, dict):
            raise ValueError("classifier_metadata.json must be an object")
        ladders = metadata.get("per_class_cefr_ladder")
        issues = validate_per_class_cefr_ladder(ladders)
        if issues:
            details = "; ".join(f"{i.class_id}: {i.message}" for i in issues)
            raise ValueError(f"Invalid per_class_cefr_ladder: {details}")
        self._metadata = metadata
        self.model_path = str(model_file)

    @staticmethod
    def _build_runtime_row(*, node: dict[str, Any], source_text: str) -> dict[str, Any]:
        features = node.get("features") if isinstance(node.get("features"), dict) else {}
        dep_signature = features.get("dep") if isinstance(features.get("dep"), list) else []
        pos_signature = features.get("pos") if isinstance(features.get("pos"), list) else []
        grammar_evidence = node.get("grammar_evidence") if isinstance(node.get("grammar_evidence"), dict) else {}
        merged_evidence = {
            "token_count": int(
                grammar_evidence.get("token_count")
                or len(dep_signature)
                or len(pos_signature)
                or len([part for part in source_text.split() if part.strip()])
            ),
            "dep_signature": grammar_evidence.get("dep_signature") if isinstance(grammar_evidence.get("dep_signature"), list) else dep_signature,
            "pos_signature": grammar_evidence.get("pos_signature") if isinstance(grammar_evidence.get("pos_signature"), list) else pos_signature,
        }
        return {
            "source_text": source_text,
            "text": source_text,
            "grammar_evidence": merged_evidence,
            "grammar_classes": node.get("grammar_classes") if isinstance(node.get("grammar_classes"), list) else [],
            "tam_profile": node.get("tam_construction"),
            "provenance": {
                "dataset_source": "runtime",
                "treebank": "runtime",
            },
        }

    def classify_node(self, *, node: dict[str, Any], source_text: str, sentence_text: str) -> dict[str, Any]:
        row = self._build_runtime_row(node=node, source_text=source_text)
        cefr = _normalize_cefr(self._predictor.predict_row(row))
        grammar_map = self._metadata.get("grammar_classes_by_cefr")
        if not isinstance(grammar_map, dict):
            grammar_map = {}
        grammar_rows = grammar_map.get(cefr) if isinstance(grammar_map.get(cefr), list) else []
        grammar_classes: list[dict[str, Any]] = []
        for item in grammar_rows:
            class_id = str(item or "").strip().lower()
            if class_id:
                grammar_classes.append({"class_id": class_id, "confidence": 0.8})
        if not grammar_classes:
            grammar_classes = [{"class_id": f"cefr::{cefr.lower()}", "confidence": 0.7}]

        notes_map = self._metadata.get("note_blueprints_by_cefr")
        if not isinstance(notes_map, dict):
            notes_map = {}
        blueprint = notes_map.get(cefr) if isinstance(notes_map.get(cefr), dict) else {}
        generated_notes = {
            "elementary_text": str(blueprint.get("elementary_text") or f"[{cefr}] elementary note").strip(),
            "intermediate_text": str(blueprint.get("intermediate_text") or f"[{cefr}] intermediate note").strip(),
            "advanced_text": str(blueprint.get("advanced_text") or f"[{cefr}] advanced note").strip(),
        }
        return {
            "cefr_level": cefr,
            "grammar_classes": grammar_classes,
            "generated_notes": generated_notes,
        }
