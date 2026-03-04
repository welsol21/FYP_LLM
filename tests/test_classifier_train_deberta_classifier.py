from __future__ import annotations

from ela_pipeline.classifier.train_deberta_classifier import _compute_class_weights


def test_compute_class_weights_none_returns_uniform_weights() -> None:
    weights = _compute_class_weights([0, 0, 1, 2], num_labels=3, strategy="none")
    assert weights == [1.0, 1.0, 1.0]


def test_compute_class_weights_balanced_upweights_rare_classes() -> None:
    weights = _compute_class_weights([0, 0, 0, 1, 2], num_labels=3, strategy="balanced")
    assert len(weights) == 3
    assert weights[0] < weights[1]
    assert weights[0] < weights[2]
    assert weights[1] == weights[2]


def test_compute_class_weights_balanced_zero_for_missing_class() -> None:
    weights = _compute_class_weights([0, 0, 1, 1], num_labels=3, strategy="balanced")
    assert weights[2] == 0.0

