"""Runtime wrapper for tabular CEFR baseline models."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib

from .train_tabular_cefr_baseline import extract_tabular_features


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
