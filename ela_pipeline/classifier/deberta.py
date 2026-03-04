"""DeBERTa-backed CEFR classifier for research/benchmark use."""

from __future__ import annotations

import json
import os
from typing import Any

from .curriculum import validate_per_class_cefr_ladder

CEFR_ALLOWED = {"A1", "A2", "B1", "B2", "C1", "C2"}


def _normalize_cefr(label: str) -> str:
    value = str(label or "").strip().upper()
    if value in CEFR_ALLOWED:
        return value
    fallback = value.replace("LABEL_", "")
    if fallback.isdigit():
        idx = int(fallback)
        ordered = ("A1", "A2", "B1", "B2", "C1", "C2")
        if 0 <= idx < len(ordered):
            return ordered[idx]
    raise ValueError(f"Invalid CEFR label from classifier: {label!r}")


class DebertaProfileClassifier:
    """Load local DeBERTa classifier and attach profile metadata by CEFR label."""

    def __init__(self, model_path: str | None, device: str = "cuda") -> None:
        path = str(model_path or "").strip()
        if not path:
            raise ValueError("classifier_model_path must be provided for classifier_provider=deberta")
        if not os.path.isdir(path):
            raise FileNotFoundError(f"classifier_model_path not found: {path}")

        metadata_path = os.path.join(path, "classifier_metadata.json")
        if not os.path.isfile(metadata_path):
            raise FileNotFoundError(
                "Missing classifier metadata file: "
                f"{metadata_path} (expected grammar classes and note blueprints mapping)."
            )

        with open(metadata_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)
        if not isinstance(metadata, dict):
            raise ValueError("classifier_metadata.json must be an object")
        ladders = metadata.get("per_class_cefr_ladder")
        issues = validate_per_class_cefr_ladder(ladders)
        if issues:
            details = "; ".join(f"{i.class_id}: {i.message}" for i in issues)
            raise ValueError(f"Invalid per_class_cefr_ladder: {details}")
        self._metadata = metadata
        self.model_path = path

        resolved_device = (device or "cuda").strip().lower()
        if resolved_device != "cuda":
            raise RuntimeError("GPU-only policy: DeBERTa classifier supports only device='cuda'")
        try:
            import torch
        except Exception as exc:  # pragma: no cover - environment-specific
            raise ImportError("torch is required for classifier_provider=deberta") from exc
        if not torch.cuda.is_available():
            raise RuntimeError("GPU-only policy: CUDA is required for DeBERTa classifier")

        # Lazy import to keep base runtime functional when transformers are absent.
        try:
            from transformers import pipeline
        except Exception as exc:  # pragma: no cover - environment-specific
            raise ImportError("transformers is required for classifier_provider=deberta") from exc

        self._pipe = pipeline(
            "text-classification",
            model=path,
            tokenizer=path,
            device=0,
            truncation=True,
        )

    def _predict_label(self, prompt: str) -> str:
        output = self._pipe(prompt)
        if not isinstance(output, list) or len(output) == 0 or not isinstance(output[0], dict):
            raise ValueError("Unexpected classifier output format")
        return str(output[0].get("label") or "").strip()

    def classify_node(self, node: dict[str, Any], source_text: str, sentence_text: str) -> dict[str, Any]:
        node_type = str(node.get("type") or "").strip()
        pos = str(node.get("part_of_speech") or "").strip()
        role = str(node.get("grammatical_role") or "").strip()
        tam = str(node.get("tam_construction") or "").strip()
        prompt = (
            "task: node_profile_classification "
            f"node_type: {node_type} "
            f"part_of_speech: {pos} "
            f"grammatical_role: {role} "
            f"tam_construction: {tam} "
            f"sentence: {sentence_text.strip()} "
            f"node_text: {source_text.strip()}"
        )

        cefr = _normalize_cefr(self._predict_label(prompt))
        return {
            "cefr_level": cefr,
        }
