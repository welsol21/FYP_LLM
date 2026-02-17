"""CEFR predictors for contract nodes."""

from __future__ import annotations

import os
from typing import Any
from typing import Protocol

CEFR_LABELS = ("A1", "A2", "B1", "B2", "C1", "C2")


def normalize_cefr_level(value: str) -> str:
    level = str(value or "").strip().upper()
    if level not in CEFR_LABELS:
        raise ValueError(f"Invalid CEFR level: {value!r}. Allowed: {'|'.join(CEFR_LABELS)}")
    return level


class CEFRPredictor(Protocol):
    def predict_level(self, node: dict, source_text: str, sentence_text: str) -> str:
        ...


class RuleBasedCEFRPredictor:
    """Fast deterministic CEFR baseline from structural/lexical signals."""

    @staticmethod
    def _word_complexity(word: str) -> int:
        w = (word or "").strip().lower()
        if not w:
            return 0
        vowels = sum(1 for ch in w if ch in "aeiouy")
        length = len(w)
        score = 0
        if length >= 11:
            score += 2
        elif length >= 8:
            score += 1
        if vowels >= 4:
            score += 1
        return score

    def predict_level(self, node: dict, source_text: str, sentence_text: str) -> str:
        node_type = str(node.get("type") or "").strip()
        text = (source_text or "").strip()
        words = [w for w in text.split() if w.strip()]
        n_words = len(words)
        n_chars = len(text)

        if node_type == "Word":
            wc = self._word_complexity(text)
            if wc <= 0:
                return "A1"
            if wc == 1:
                return "A2"
            if wc == 2:
                return "B1"
            return "B2"

        # Phrase/Sentence rough complexity heuristic.
        score = 0
        if n_words >= 20:
            score += 3
        elif n_words >= 12:
            score += 2
        elif n_words >= 7:
            score += 1
        if n_chars >= 120:
            score += 2
        elif n_chars >= 70:
            score += 1
        if str(node.get("mood") or "").lower() == "modal":
            score += 1
        if str(node.get("aspect") or "").lower() == "perfect":
            score += 1
        if str(node.get("finiteness") or "").lower() == "non-finite":
            score += 1

        if score <= 1:
            return "A2"
        if score == 2:
            return "B1"
        if score in {3, 4}:
            return "B2"
        if score == 5:
            return "C1"
        return "C2"


class MLSklearnCEFRPredictor:
    """Load sklearn-compatible CEFR classifier from joblib and run node-level prediction."""

    def __init__(self, model_path: str) -> None:
        path = (model_path or "").strip()
        if not path:
            raise ValueError("cefr_model_path must be non-empty for ml provider")
        if not os.path.isfile(path):
            raise FileNotFoundError(f"CEFR model file not found: {path}")
        try:
            import joblib
        except Exception as exc:  # pragma: no cover - env dependent
            raise ImportError("joblib is required for ml CEFR provider") from exc
        self._model = joblib.load(path)
        self.model_path = path

    @staticmethod
    def _build_feature_row(node: dict, source_text: str, sentence_text: str) -> dict:
        text = (source_text or "").strip()
        words = [w for w in text.split() if w.strip()]
        return {
            "node_type": str(node.get("type") or ""),
            "part_of_speech": str(node.get("part_of_speech") or ""),
            "grammatical_role": str(node.get("grammatical_role") or ""),
            "word_count": len(words),
            "char_count": len(text),
            "sentence_word_count": len([w for w in (sentence_text or "").split() if w.strip()]),
            "is_modal": 1 if str(node.get("mood") or "").lower() == "modal" else 0,
            "is_perfect": 1 if str(node.get("aspect") or "").lower() == "perfect" else 0,
            "is_non_finite": 1 if str(node.get("finiteness") or "").lower() == "non-finite" else 0,
        }

    def predict_level(self, node: dict, source_text: str, sentence_text: str) -> str:
        try:
            import pandas as pd
        except Exception as exc:  # pragma: no cover - env dependent
            raise ImportError("pandas is required for ml CEFR provider") from exc
        row = self._build_feature_row(node, source_text, sentence_text)
        pred = self._model.predict(pd.DataFrame([row]))[0]
        return normalize_cefr_level(str(pred))


class T5CEFRPredictor:
    """Run CEFR classification with local T5 model."""

    def __init__(self, model_path: str, device: str = "cuda") -> None:
        path = (model_path or "").strip()
        if not path:
            raise ValueError("cefr_model_path must be non-empty for t5 provider")
        if not os.path.isdir(path):
            raise FileNotFoundError(f"CEFR model directory not found: {path}")
        try:
            import torch
            from transformers import T5ForConditionalGeneration, T5Tokenizer
        except Exception as exc:  # pragma: no cover - env dependent
            raise ImportError("transformers + torch are required for t5 CEFR provider") from exc

        resolved_device = device
        if resolved_device != "cuda":
            raise RuntimeError("GPU-only policy: CEFR T5 provider supports only device='cuda'")
        if not torch.cuda.is_available():
            raise RuntimeError("GPU-only policy: CUDA is required for CEFR T5 inference")

        self._torch = torch
        self._tokenizer = T5Tokenizer.from_pretrained(path)
        self._model = T5ForConditionalGeneration.from_pretrained(path).to(resolved_device)
        self._model.eval()
        self.device = resolved_device
        self.model_path = path

    @staticmethod
    def _tam_bucket(node: dict) -> str:
        raw = node.get("tam_construction")
        if isinstance(raw, str) and raw.strip():
            return raw.strip().lower()
        return "none"

    @staticmethod
    def _format_morph(features: Any) -> str:
        if not isinstance(features, dict):
            return "UNKNOWN"
        vals = []
        for k, v in features.items():
            if v in (None, "", "null"):
                continue
            vals.append(f"{k}:{v}")
        return ", ".join(vals) if vals else "UNKNOWN"

    @classmethod
    def _build_prompt(cls, node: dict, source_text: str, sentence_text: str) -> str:
        node_type = str(node.get("type") or "")
        tam_bucket = cls._tam_bucket(node)
        pos = str(node.get("part_of_speech") or "UNKNOWN")
        dep = str(node.get("dep_label") or node.get("grammatical_role") or "UNKNOWN")
        text = (source_text or "").strip()
        sentence = (sentence_text or "").strip()

        if node_type == "Sentence":
            return (
                f"task: predict_cefr_level "
                f"template_version: v1 "
                f"node_type: Sentence "
                f"tam_bucket: {tam_bucket} "
                f"sentence: {sentence} "
                f"pos: {pos} "
                f"dep: {dep}"
            )
        if node_type == "Phrase":
            return (
                f"task: predict_cefr_level "
                f"template_version: v1 "
                f"node_type: Phrase "
                f"tam_bucket: {tam_bucket} "
                f"sentence: {sentence} "
                f"phrase: {text} "
                f"pos: {pos} "
                f"dep: {dep}"
            )
        return (
            f"task: predict_cefr_level "
            f"template_version: v1 "
            f"node_type: Word "
            f"tam_bucket: {tam_bucket} "
            f"sentence: {sentence} "
            f"word: {text} "
            f"pos: {pos} "
            f"tag: {str(node.get('tense') or 'UNKNOWN')} "
            f"dep: {dep} "
            f"morph: {cls._format_morph(node.get('features'))}"
        )

    def predict_level(self, node: dict, source_text: str, sentence_text: str) -> str:
        prompt = self._build_prompt(node=node, source_text=source_text, sentence_text=sentence_text)
        encoded = self._tokenizer(prompt, return_tensors="pt", truncation=True, max_length=512)
        encoded = {k: v.to(self.device) for k, v in encoded.items()}
        with self._torch.no_grad():
            generated = self._model.generate(
                **encoded,
                max_length=8,
                num_beams=4,
                early_stopping=True,
            )
        text = self._tokenizer.decode(generated[0], skip_special_tokens=True).strip()
        return normalize_cefr_level(text)
