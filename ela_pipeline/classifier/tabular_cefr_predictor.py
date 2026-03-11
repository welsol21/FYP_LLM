"""Runtime wrapper for tabular CEFR baseline models."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import joblib

from .class_taxonomy import normalize_grammar_class_id
from .grammar_blueprints import build_note_blueprints, class_cefr_level
from .grammar_rules import map_pedagogical_grammar_classes
from .curriculum import validate_per_class_cefr_ladder
from .train_tabular_cefr_baseline import extract_tabular_features, project_feature_profile

CEFR_ALLOWED = {"A1", "A2", "B1", "B2", "C1", "C2"}
CEFR_ORDER = ("A1", "A2", "B1", "B2", "C1", "C2")
CEFR_RANK = {label: idx for idx, label in enumerate(CEFR_ORDER)}


def _normalize_cefr(label: Any) -> str:
    value_raw = str(label or "").strip()
    value = value_raw.upper()
    if value in CEFR_ALLOWED:
        return value
    # Accept legacy/indexed labels from sklearn/xgboost models.
    # Supported encodings:
    # - 0..5 -> A1..C2
    # - 1..6 -> A1..C2
    # - float strings like "4.0"
    try:
        numeric = int(float(value_raw))
    except (TypeError, ValueError):
        numeric = None
    if numeric is not None:
        if 0 <= numeric < len(CEFR_ORDER):
            return CEFR_ORDER[numeric]
        if 1 <= numeric <= len(CEFR_ORDER):
            return CEFR_ORDER[numeric - 1]
    raise ValueError(f"Invalid CEFR label from tabular classifier: {label!r}")


class TabularCefrPredictor:
    def __init__(self, model: Any, *, feature_profile: str = "runtime_stable") -> None:
        self._model = model
        self._feature_profile = str(feature_profile or "runtime_stable").strip().lower()

    @classmethod
    def from_path(cls, model_path: str, *, feature_profile: str = "runtime_stable") -> "TabularCefrPredictor":
        path = Path(model_path)
        if not path.is_file():
            raise FileNotFoundError(f"tabular CEFR model not found: {model_path}")
        return cls(joblib.load(path), feature_profile=feature_profile)

    def predict_row(self, row: dict[str, Any]) -> str:
        features = project_feature_profile(
            extract_tabular_features(row),
            profile=self._feature_profile,
        )
        result = self._model.predict([features])
        if not result:
            return ""
        return str(result[0]).strip().upper()

    def predict_rows(self, rows: list[dict[str, Any]]) -> list[str]:
        feature_rows = [
            project_feature_profile(extract_tabular_features(row), profile=self._feature_profile)
            for row in rows
        ]
        out = self._model.predict(feature_rows)
        return [str(item).strip().upper() for item in out]


class TabularJointProfilePredictor:
    """Joint predictor: CEFR + primary grammar class + note blueprint id."""

    def __init__(
        self,
        model: Any,
        *,
        feature_profile: str = "runtime_stable",
        joint_label_order: list[str] | None = None,
    ) -> None:
        self._model = model
        self._feature_profile = str(feature_profile or "runtime_stable").strip().lower()
        self._joint_label_order = list(joint_label_order or [])

    @classmethod
    def from_path(cls, model_path: str, *, feature_profile: str = "runtime_stable") -> "TabularJointProfilePredictor":
        path = Path(model_path)
        if not path.is_file():
            raise FileNotFoundError(f"tabular joint model not found: {model_path}")
        return cls(joblib.load(path), feature_profile=feature_profile)

    def predict_row(self, row: dict[str, Any]) -> tuple[str, str]:
        features = project_feature_profile(
            extract_tabular_features(row),
            profile=self._feature_profile,
        )
        result = self._model.predict([features])
        if result is None or len(result) == 0:
            return "", ""
        item = result[0]
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            return str(item[0]).strip(), str(item[1]).strip().lower()
        if hasattr(item, "__len__") and not isinstance(item, str) and len(item) >= 2:  # numpy row
            return str(item[0]).strip(), str(item[1]).strip().lower()
        if isinstance(item, (int, float)):
            idx = int(item)
            if 0 <= idx < len(self._joint_label_order):
                label = str(self._joint_label_order[idx]).strip()
                if "|" in label:
                    cefr, grammar_class = label.split("|", 1)
                    return cefr.strip(), grammar_class.strip().lower()
        scalar = str(item).strip()
        if scalar.isdigit():
            idx = int(scalar)
            if 0 <= idx < len(self._joint_label_order):
                label = str(self._joint_label_order[idx]).strip()
                if "|" in label:
                    cefr, grammar_class = label.split("|", 1)
                    return cefr.strip(), grammar_class.strip().lower()
        if "|" in scalar:
            cefr, grammar_class = scalar.split("|", 1)
            return cefr.strip(), grammar_class.strip().lower()
        return scalar, ""


class TabularProfileClassifier:
    """CEFR classifier backed by the tabular baseline plus runtime metadata."""

    def __init__(self, model_path: str | None) -> None:
        path = Path(str(model_path or "").strip())
        if not str(path):
            raise ValueError("classifier_model_path must be provided for classifier_provider=tabular")
        if path.is_dir():
            joint_model_file = path / "best_tabular_joint_profile.joblib"
            model_file = path / "best_tabular_cefr_baseline.joblib"
            metadata_file = path / "classifier_metadata.json"
        else:
            joint_model_file = Path("")
            model_file = path
            metadata_file = path.parent / "classifier_metadata.json"
        if not model_file.is_file() and not joint_model_file.is_file():
            raise FileNotFoundError(
                f"tabular classifier model not found: {model_file} and joint model not found: {joint_model_file}"
            )
        if not metadata_file.is_file():
            raise FileNotFoundError(f"Missing classifier metadata file: {metadata_file}")

        with metadata_file.open("r", encoding="utf-8") as f:
            metadata = json.load(f)
        if not isinstance(metadata, dict):
            raise ValueError("classifier_metadata.json must be an object")
        summary_path = model_file.parent / "tabular_cefr_baseline_summary.json"
        summary = {}
        if summary_path.is_file():
            with summary_path.open("r", encoding="utf-8") as f:
                loaded_summary = json.load(f)
            if isinstance(loaded_summary, dict):
                summary = loaded_summary
        feature_profile = str(summary.get("feature_profile") or "runtime_stable").strip().lower()
        self._joint_mode = bool(joint_model_file.is_file())
        joint_label_order = metadata.get("joint_label_order")
        if not isinstance(joint_label_order, list):
            joint_label_order = []
        if self._joint_mode:
            self._predictor = TabularJointProfilePredictor(
                joblib.load(joint_model_file),
                feature_profile=feature_profile,
                joint_label_order=[str(item) for item in joint_label_order if str(item).strip()],
            )
        else:
            self._predictor = TabularCefrPredictor.from_path(str(model_file), feature_profile=feature_profile)
        ladders = metadata.get("per_class_cefr_ladder")
        issues = validate_per_class_cefr_ladder(ladders)
        if issues:
            details = "; ".join(f"{i.class_id}: {i.message}" for i in issues)
            raise ValueError(f"Invalid per_class_cefr_ladder: {details}")
        self._metadata = metadata
        self.model_path = str(joint_model_file if self._joint_mode else model_file)
        self.feature_profile = feature_profile
        self.supports_joint_profiles = self._joint_mode

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

    def _resolve_note_blueprints(self, *, cefr: str, class_id: str, node: dict[str, Any]) -> dict[str, str]:
        generated = (
            build_note_blueprints(
                grammar_classes=[class_id],
                cefr_level=cefr,
                node_type=str(node.get("type") or ""),
                content=str(node.get("content") or ""),
                grammatical_role=str(node.get("grammatical_role") or ""),
                tam_construction=str(node.get("tam_construction") or ""),
                part_of_speech=str(node.get("part_of_speech") or ""),
                tense=str(node.get("tense") or ""),
            )
            if class_id
            else {}
        )
        required_keys = ("elementary_text", "intermediate_text", "advanced_text")
        if all(str(generated.get(k) or "").strip() for k in required_keys):
            return {k: str(generated.get(k) or "").strip() for k in required_keys}

        per_cefr = self._metadata.get("note_blueprints_by_cefr")
        if isinstance(per_cefr, dict):
            candidate = per_cefr.get(cefr)
            if isinstance(candidate, dict):
                fallback = {k: str(candidate.get(k) or "").strip() for k in required_keys}
                if all(fallback[k] for k in required_keys):
                    return fallback

        return {
            "elementary_text": f"[{cefr}] identify the grammar pattern in this node.",
            "intermediate_text": f"[{cefr}] explain the grammar pattern and its meaning in context.",
            "advanced_text": f"[{cefr}] analyze the grammar pattern and its discourse function in context.",
        }

    @staticmethod
    def _max_cefr(*levels: str) -> str:
        valid = [item for item in levels if item in CEFR_RANK]
        if not valid:
            return "B1"
        return max(valid, key=lambda item: CEFR_RANK[item])

    @staticmethod
    def _rule_candidates(node: dict[str, Any], source_text: str) -> list[str]:
        features = node.get("features") if isinstance(node.get("features"), dict) else {}
        dep_labels = features.get("dep") if isinstance(features.get("dep"), list) else []
        return map_pedagogical_grammar_classes(
            tense=str(node.get("tense") or ""),
            aspect=str(node.get("aspect") or ""),
            mood=str(node.get("mood") or ""),
            voice=str(node.get("voice") or ""),
            tam_construction=str(node.get("tam_construction") or ""),
            dep_labels=dep_labels,
            content=str(node.get("content") or source_text or ""),
            node_type=str(node.get("type") or ""),
            part_of_speech=str(node.get("part_of_speech") or ""),
        )

    def classify_node(self, *, node: dict[str, Any], source_text: str, sentence_text: str) -> dict[str, Any]:
        row = self._build_runtime_row(node=node, source_text=source_text)
        if self._joint_mode:
            pred_cefr, pred_class = self._predictor.predict_row(row)
            rule_candidates = self._rule_candidates(node=node, source_text=source_text)
            normalized_rules: list[str] = []
            for item in rule_candidates:
                normalized = normalize_grammar_class_id(str(item or "").strip().lower())
                if normalized and normalized not in normalized_rules:
                    normalized_rules.append(normalized)

            predicted_class = normalize_grammar_class_id(str(pred_class or "").strip().lower())
            class_candidates = list(normalized_rules)
            if not class_candidates and predicted_class:
                class_candidates.append(predicted_class)
            primary_class = class_candidates[0] if class_candidates else predicted_class

            predicted_cefr = ""
            try:
                predicted_cefr = _normalize_cefr(pred_cefr)
            except ValueError:
                predicted_cefr = ""
            class_floor = ""
            if primary_class:
                class_floor = str(class_cefr_level(primary_class) or "").strip().upper()
            node_type = str(node.get("type") or "").strip().lower()
            if node_type in {"word", "phrase"}:
                cefr = class_floor or predicted_cefr or "B1"
            else:
                cefr = self._max_cefr(predicted_cefr, class_floor)

            note_blueprints = self._resolve_note_blueprints(cefr=cefr, class_id=primary_class, node=node)
            grammar_classes_payload: list[dict[str, Any]] = []
            if class_candidates:
                for idx, cid in enumerate(class_candidates):
                    grammar_classes_payload.append(
                        {"class_id": cid, "confidence": round(max(0.4, 0.92 - idx * 0.12), 2)}
                    )
            return {
                "cefr_level": cefr,
                "grammar_classes": grammar_classes_payload,
                "generated_notes": note_blueprints,
            }

        cefr = _normalize_cefr(self._predictor.predict_row(row))
        return {
            "cefr_level": cefr,
        }
