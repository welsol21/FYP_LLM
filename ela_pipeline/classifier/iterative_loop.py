"""Iterative quality loop runner until repeated full-pass is reached."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .quality_loop import GateResult


@dataclass(frozen=True)
class IterationRecord:
    iteration: int
    all_passed: bool
    failed_gates: tuple[str, ...]


def run_iterative_improvement_loop(
    *,
    evaluate_full_run: Callable[[int], list[GateResult]],
    required_consecutive_passes: int = 3,
    max_iterations: int = 100,
) -> tuple[list[IterationRecord], bool]:
    if required_consecutive_passes < 1:
        raise ValueError("required_consecutive_passes must be >= 1")
    if max_iterations < 1:
        raise ValueError("max_iterations must be >= 1")

    consecutive = 0
    records: list[IterationRecord] = []
    for iteration in range(1, max_iterations + 1):
        results = evaluate_full_run(iteration)
        failed = tuple(sorted(r.gate for r in results if not r.passed))
        all_passed = len(failed) == 0
        if all_passed:
            consecutive += 1
        else:
            consecutive = 0
        records.append(
            IterationRecord(
                iteration=iteration,
                all_passed=all_passed,
                failed_gates=failed,
            )
        )
        if consecutive >= required_consecutive_passes:
            return records, True
    return records, False
