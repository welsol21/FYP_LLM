"""Regression checks for feedback retraining artifacts."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class RegressionThresholds:
    min_eval_exact_match_delta: float = 0.0
    max_eval_loss_increase: float = 0.0
    min_accepted_note_rate_delta: float = 0.0
    max_fallback_rate_increase: float = 0.0
    max_rejected_nodes_increase: int = 0
    max_semantic_mismatch_rate_increase: float = 0.0


def _load_json(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _as_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return default
    return default


def _as_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value))
        except ValueError:
            return default
    return default


def _add_check(checks: list[dict[str, Any]], name: str, passed: bool, details: dict[str, Any]) -> None:
    checks.append({"name": name, "passed": bool(passed), "details": details})


def evaluate_feedback_regression(
    *,
    baseline_train_report: dict[str, Any],
    candidate_train_report: dict[str, Any],
    baseline_qc_report: dict[str, Any],
    candidate_qc_report: dict[str, Any],
    thresholds: RegressionThresholds,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    base_eval = baseline_train_report.get("eval_metrics") or {}
    cand_eval = candidate_train_report.get("eval_metrics") or {}
    base_qc_agg = (baseline_qc_report.get("aggregate") or {}) if isinstance(baseline_qc_report, dict) else {}
    cand_qc_agg = (candidate_qc_report.get("aggregate") or {}) if isinstance(candidate_qc_report, dict) else {}

    base_em = _as_float(base_eval.get("eval_exact_match"))
    cand_em = _as_float(cand_eval.get("eval_exact_match"))
    _add_check(
        checks,
        "train_eval_exact_match_non_regression",
        cand_em >= (base_em + thresholds.min_eval_exact_match_delta),
        {"baseline": base_em, "candidate": cand_em, "min_delta": thresholds.min_eval_exact_match_delta},
    )

    base_loss = _as_float(base_eval.get("eval_loss"), default=0.0)
    cand_loss = _as_float(cand_eval.get("eval_loss"), default=0.0)
    _add_check(
        checks,
        "train_eval_loss_non_increase",
        cand_loss <= (base_loss + thresholds.max_eval_loss_increase),
        {"baseline": base_loss, "candidate": cand_loss, "max_increase": thresholds.max_eval_loss_increase},
    )

    base_probe_count = _as_int(baseline_qc_report.get("probe_count"), default=0)
    cand_probe_count = _as_int(candidate_qc_report.get("probe_count"), default=0)
    base_nodes = _as_int(base_qc_agg.get("total_nodes"), default=0)
    cand_nodes = _as_int(cand_qc_agg.get("total_nodes"), default=0)
    _add_check(
        checks,
        "contract_validity_baseline_qc_present",
        base_probe_count > 0 and base_nodes > 0,
        {"probe_count": base_probe_count, "total_nodes": base_nodes},
    )
    _add_check(
        checks,
        "contract_validity_candidate_qc_present",
        cand_probe_count > 0 and cand_nodes > 0,
        {"probe_count": cand_probe_count, "total_nodes": cand_nodes},
    )

    base_accept = _as_float(base_qc_agg.get("accepted_note_rate"))
    cand_accept = _as_float(cand_qc_agg.get("accepted_note_rate"))
    _add_check(
        checks,
        "qc_accepted_note_rate_non_regression",
        cand_accept >= (base_accept + thresholds.min_accepted_note_rate_delta),
        {
            "baseline": base_accept,
            "candidate": cand_accept,
            "min_delta": thresholds.min_accepted_note_rate_delta,
        },
    )

    base_fallback = _as_float(base_qc_agg.get("fallback_rate"))
    cand_fallback = _as_float(cand_qc_agg.get("fallback_rate"))
    _add_check(
        checks,
        "qc_fallback_rate_non_increase",
        cand_fallback <= (base_fallback + thresholds.max_fallback_rate_increase),
        {
            "baseline": base_fallback,
            "candidate": cand_fallback,
            "max_increase": thresholds.max_fallback_rate_increase,
        },
    )

    base_rejected = _as_int(base_qc_agg.get("rejected_nodes_total"))
    cand_rejected = _as_int(cand_qc_agg.get("rejected_nodes_total"))
    _add_check(
        checks,
        "qc_rejected_nodes_non_increase",
        cand_rejected <= (base_rejected + thresholds.max_rejected_nodes_increase),
        {
            "baseline": base_rejected,
            "candidate": cand_rejected,
            "max_increase": thresholds.max_rejected_nodes_increase,
        },
    )

    base_semantic = _as_float(base_qc_agg.get("semantic_mismatch_rate"))
    cand_semantic = _as_float(cand_qc_agg.get("semantic_mismatch_rate"))
    _add_check(
        checks,
        "qc_semantic_mismatch_non_increase",
        cand_semantic <= (base_semantic + thresholds.max_semantic_mismatch_rate_increase),
        {
            "baseline": base_semantic,
            "candidate": cand_semantic,
            "max_increase": thresholds.max_semantic_mismatch_rate_increase,
        },
    )

    return {
        "overall_passed": all(item["passed"] for item in checks),
        "checks": checks,
        "baseline": {
            "eval_metrics": base_eval,
            "qc_aggregate": base_qc_agg,
        },
        "candidate": {
            "eval_metrics": cand_eval,
            "qc_aggregate": cand_qc_agg,
        },
    }


def _default_output_path() -> str:
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"docs/reports/feedback_retrain_regression_{ts}.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Check feedback retrain regression gates")
    parser.add_argument("--baseline-train-report", required=True)
    parser.add_argument("--candidate-train-report", required=True)
    parser.add_argument("--baseline-qc-report", required=True)
    parser.add_argument("--candidate-qc-report", required=True)
    parser.add_argument("--output", default="")
    parser.add_argument("--min-eval-exact-match-delta", type=float, default=0.0)
    parser.add_argument("--max-eval-loss-increase", type=float, default=0.0)
    parser.add_argument("--min-accepted-note-rate-delta", type=float, default=0.0)
    parser.add_argument("--max-fallback-rate-increase", type=float, default=0.0)
    parser.add_argument("--max-rejected-nodes-increase", type=int, default=0)
    parser.add_argument("--max-semantic-mismatch-rate-increase", type=float, default=0.0)
    args = parser.parse_args()

    baseline_train = _load_json(args.baseline_train_report)
    candidate_train = _load_json(args.candidate_train_report)
    baseline_qc = _load_json(args.baseline_qc_report)
    candidate_qc = _load_json(args.candidate_qc_report)

    report = evaluate_feedback_regression(
        baseline_train_report=baseline_train,
        candidate_train_report=candidate_train,
        baseline_qc_report=baseline_qc,
        candidate_qc_report=candidate_qc,
        thresholds=RegressionThresholds(
            min_eval_exact_match_delta=args.min_eval_exact_match_delta,
            max_eval_loss_increase=args.max_eval_loss_increase,
            min_accepted_note_rate_delta=args.min_accepted_note_rate_delta,
            max_fallback_rate_increase=args.max_fallback_rate_increase,
            max_rejected_nodes_increase=args.max_rejected_nodes_increase,
            max_semantic_mismatch_rate_increase=args.max_semantic_mismatch_rate_increase,
        ),
    )
    out = args.output or _default_output_path()
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(out)
    print(json.dumps({"overall_passed": report["overall_passed"]}, indent=2))
    if not report["overall_passed"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
