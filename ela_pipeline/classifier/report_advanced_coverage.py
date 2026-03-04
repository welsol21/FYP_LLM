"""Merged advanced coverage reporting and readiness thresholds."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any


ADVANCED_THRESHOLDS = {
    ("B2", "past_perfect"): 100,
    ("B2", "passive_voice"): 100,
    ("C1", "modal_perfect"): 50,
    ("C2", "future_perfect"): 50,
}


def _read_jsonl_counts(path: str) -> tuple[Counter[str], Counter[tuple[str, str]], int]:
    cefr_counts: Counter[str] = Counter()
    class_support: Counter[tuple[str, str]] = Counter()
    total = 0
    src = Path(path)
    if not src.is_file():
        return cefr_counts, class_support, total
    with src.open("r", encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            cefr = str(row.get("cefr_level") or "").strip().upper()
            if not cefr:
                continue
            total += 1
            cefr_counts[cefr] += 1
            for class_id in row.get("grammar_classes", []):
                class_support[(cefr, class_id)] += 1
    return cefr_counts, class_support, total


def _counter_from_rows(rows: list[dict[str, Any]]) -> Counter[tuple[str, str]]:
    support: Counter[tuple[str, str]] = Counter()
    for row in rows:
        cefr = str(row.get("cefr_level") or "").strip().upper()
        class_id = str(row.get("class_id") or "").strip()
        count = int(row.get("count") or 0)
        if cefr and class_id and count > 0:
            support[(cefr, class_id)] += count
    return support


def _cefr_counter_from_map(raw: dict[str, Any]) -> Counter[str]:
    out: Counter[str] = Counter()
    for key, value in (raw or {}).items():
        cefr = str(key or "").strip().upper()
        count = int(value or 0)
        if cefr and count > 0:
            out[cefr] += count
    return out


def _summary_block(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary")
    if isinstance(summary, dict):
        return summary
    return payload


def build_advanced_coverage_report(
    *,
    ud_train_path: str,
    ud_dev_path: str,
    ud_test_path: str,
    oanc_probe_report_path: str,
    oanc_targeted_report_path: str,
    masc_probe_report_path: str,
    pmc_probe_report_path: str = "",
) -> dict[str, Any]:
    ud_train_cefr, ud_train_support, ud_train_total = _read_jsonl_counts(ud_train_path)
    ud_dev_cefr, ud_dev_support, ud_dev_total = _read_jsonl_counts(ud_dev_path)
    ud_test_cefr, ud_test_support, ud_test_total = _read_jsonl_counts(ud_test_path)

    oanc_probe = _summary_block(json.loads(Path(oanc_probe_report_path).read_text(encoding="utf-8")))
    oanc_targeted = _summary_block(json.loads(Path(oanc_targeted_report_path).read_text(encoding="utf-8")))
    masc_probe = _summary_block(json.loads(Path(masc_probe_report_path).read_text(encoding="utf-8")))

    oanc_support = _counter_from_rows(oanc_probe.get("mapped_class_support", []))
    oanc_support.update(_counter_from_rows(oanc_targeted.get("mapped_class_support", [])))
    oanc_cefr = _cefr_counter_from_map(oanc_probe.get("mapped_cefr_counts", {}))
    oanc_cefr.update(_cefr_counter_from_map(oanc_targeted.get("mapped_cefr_counts", {})))

    masc_support = _counter_from_rows(masc_probe.get("mapped_class_support", []))
    masc_cefr = _cefr_counter_from_map(masc_probe.get("mapped_cefr_counts", {}))
    pmc_support: Counter[tuple[str, str]] = Counter()
    pmc_cefr: Counter[str] = Counter()
    pmc_total = 0
    if str(pmc_probe_report_path or "").strip():
        pmc_probe = _summary_block(json.loads(Path(pmc_probe_report_path).read_text(encoding="utf-8")))
        pmc_support = _counter_from_rows(pmc_probe.get("mapped_class_support", []))
        pmc_cefr = _cefr_counter_from_map(pmc_probe.get("mapped_cefr_counts", {}))
        pmc_total = int(pmc_probe.get("mapped_rows_before_gates", 0))

    train_support = Counter(ud_train_support)
    train_support.update(oanc_support)
    train_support.update(pmc_support)
    control_support = Counter(ud_dev_support)
    control_support.update(ud_test_support)
    control_support.update(masc_support)

    threshold_results: list[dict[str, Any]] = []
    overall_ready = True
    for (cefr, class_id), required in ADVANCED_THRESHOLDS.items():
        train_count = train_support[(cefr, class_id)]
        control_count = control_support[(cefr, class_id)]
        ready = train_count >= required and control_count >= 1
        if not ready:
            overall_ready = False
        threshold_results.append(
            {
                "cefr_level": cefr,
                "class_id": class_id,
                "required_train_support": required,
                "observed_train_support": train_count,
                "observed_control_support": control_count,
                "ready": ready,
            }
        )

    return {
        "sources": {
            "ud_train_total": ud_train_total,
            "ud_dev_total": ud_dev_total,
            "ud_test_total": ud_test_total,
            "oanc_mapped_total": int(oanc_probe.get("mapped_rows_before_gates", 0))
            + int(oanc_targeted.get("mapped_rows_before_gates", 0)),
            "masc_mapped_total": int(masc_probe.get("mapped_rows_before_gates", 0)),
            "pmc_mapped_total": pmc_total,
        },
        "source_cefr_counts": {
            "ud_train": dict(sorted(ud_train_cefr.items())),
            "ud_dev": dict(sorted(ud_dev_cefr.items())),
            "ud_test": dict(sorted(ud_test_cefr.items())),
            "oanc_pre_gate": dict(sorted(oanc_cefr.items())),
            "masc_pre_gate": dict(sorted(masc_cefr.items())),
            "pmc_pre_gate": dict(sorted(pmc_cefr.items())),
        },
        "advanced_thresholds": threshold_results,
        "overall_advanced_readiness": overall_ready,
    }
