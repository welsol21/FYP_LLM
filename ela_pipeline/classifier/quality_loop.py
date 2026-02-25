"""Quality gates and retry loop telemetry for classifier curriculum pipeline."""

from __future__ import annotations

from dataclasses import asdict
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class GateResult:
    gate: str
    passed: bool
    details: dict[str, Any]


@dataclass(frozen=True)
class QualityEvent:
    run_id: str
    stage: str
    gate: str
    passed: bool
    metrics: dict[str, Any]
    thresholds: dict[str, Any]
    attempt: int


@dataclass(frozen=True)
class RepairAction:
    run_id: str
    stage: str
    gate: str
    attempt: int
    action: str
    reason: str


DEFAULT_GATE_THRESHOLDS: dict[str, dict[str, float]] = {
    "kb_generation": {
        "class_coverage": 0.95,
        "level_balance": 0.85,
        "duplicate_ratio_max": 0.10,
        "invalid_blueprint_ratio_max": 0.03,
    },
    "spacy_enrichment": {
        "parse_success_rate": 0.98,
        "required_feature_coverage": 0.95,
        "structural_anomaly_rate_max": 0.02,
    },
    "classifier": {
        "macro_f1": 0.82,
        "min_class_recall": 0.70,
        "ece_max": 0.12,
    },
    "contract": {
        "schema_pass_rate": 0.995,
        "consistency_pass_rate": 0.98,
        "blueprint_completeness": 0.995,
    },
    "nlg": {
        "note_relevance": 0.90,
        "level_style_fit": 0.88,
        "blueprint_traceability": 0.98,
        "hallucination_rate_max": 0.03,
    },
}


def evaluate_quality_gate(gate: str, metrics: dict[str, float], thresholds: dict[str, float] | None = None) -> GateResult:
    gate_name = str(gate or "").strip()
    if gate_name not in DEFAULT_GATE_THRESHOLDS:
        raise ValueError(f"Unknown gate: {gate!r}")
    limits = dict(DEFAULT_GATE_THRESHOLDS[gate_name])
    if thresholds:
        limits.update(thresholds)

    checks: dict[str, bool] = {}
    for key, threshold in limits.items():
        value = float(metrics.get(key, 0.0))
        if key.endswith("_max"):
            checks[key] = value <= float(threshold)
        elif key.endswith("_ratio_max"):
            checks[key] = value <= float(threshold)
        else:
            checks[key] = value >= float(threshold)

    return GateResult(
        gate=gate_name,
        passed=all(checks.values()),
        details={"checks": checks, "metrics": dict(metrics), "thresholds": limits},
    )


def run_stage_with_retry(
    *,
    run_id: str,
    stage: str,
    gate: str,
    measure_metrics: Callable[[int], dict[str, float]],
    build_repair_action: Callable[[int, GateResult], tuple[str, str]] | None = None,
    max_attempts: int = 3,
    thresholds: dict[str, float] | None = None,
) -> tuple[GateResult, list[QualityEvent], list[RepairAction]]:
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")

    events: list[QualityEvent] = []
    repairs: list[RepairAction] = []
    result: GateResult | None = None

    for attempt in range(1, max_attempts + 1):
        metrics = measure_metrics(attempt)
        result = evaluate_quality_gate(gate=gate, metrics=metrics, thresholds=thresholds)
        limits = result.details["thresholds"]
        events.append(
            QualityEvent(
                run_id=run_id,
                stage=stage,
                gate=gate,
                passed=result.passed,
                metrics=dict(metrics),
                thresholds=dict(limits),
                attempt=attempt,
            )
        )
        if result.passed:
            break
        if attempt < max_attempts:
            if build_repair_action is not None:
                action, reason = build_repair_action(attempt, result)
            else:
                action, reason = ("rerun_stage", "gate_failed")
            repairs.append(
                RepairAction(
                    run_id=run_id,
                    stage=stage,
                    gate=gate,
                    attempt=attempt,
                    action=action,
                    reason=reason,
                )
            )

    assert result is not None
    return result, events, repairs


def persist_quality_telemetry(
    *,
    output_dir: str,
    quality_events: list[QualityEvent],
    repair_actions: list[RepairAction],
) -> dict[str, str]:
    base = Path(output_dir)
    base.mkdir(parents=True, exist_ok=True)
    events_path = base / "quality_events.jsonl"
    repairs_path = base / "repair_actions.jsonl"

    with events_path.open("w", encoding="utf-8") as f:
        for item in quality_events:
            f.write(json.dumps(asdict(item), ensure_ascii=False) + "\n")
    with repairs_path.open("w", encoding="utf-8") as f:
        for item in repair_actions:
            f.write(json.dumps(asdict(item), ensure_ascii=False) + "\n")

    return {
        "quality_events": str(events_path),
        "repair_actions": str(repairs_path),
    }
