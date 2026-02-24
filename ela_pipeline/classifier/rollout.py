"""Phased rollout configuration for grammar curriculum classifier."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PhaseEstimate:
    mvp_weeks: str
    stable_weeks: str


@dataclass(frozen=True)
class PhaseSpec:
    phase_id: str
    levels: tuple[str, ...]
    estimate: PhaseEstimate


PHASES: dict[str, PhaseSpec] = {
    "phase1": PhaseSpec(
        phase_id="phase1",
        levels=("A1", "A2", "B1"),
        estimate=PhaseEstimate(mvp_weeks="1.5-2.5", stable_weeks="3-4"),
    ),
    "phase2": PhaseSpec(
        phase_id="phase2",
        levels=("B2",),
        estimate=PhaseEstimate(mvp_weeks="1-2.5", stable_weeks="1-2.5"),
    ),
    "phase3": PhaseSpec(
        phase_id="phase3",
        levels=("C1", "C2"),
        estimate=PhaseEstimate(mvp_weeks="2-4", stable_weeks="2-4"),
    ),
}

PHASE_ORDER = ("phase1", "phase2", "phase3")
FULL_LADDER_TARGET_WEEKS = "6-10"


def get_phase(phase_id: str) -> PhaseSpec:
    pid = str(phase_id or "").strip().lower()
    if pid not in PHASES:
        raise ValueError(f"Unknown phase: {phase_id!r}")
    return PHASES[pid]


def can_start_phase(phase_id: str, repeated_pass_runs: int, min_repeated_pass_runs: int = 3) -> bool:
    pid = str(phase_id or "").strip().lower()
    if pid == "phase1":
        return True
    if pid not in PHASES:
        raise ValueError(f"Unknown phase: {phase_id!r}")
    if min_repeated_pass_runs < 1:
        raise ValueError("min_repeated_pass_runs must be >= 1")
    return int(repeated_pass_runs) >= int(min_repeated_pass_runs)


def build_phase_time_summary() -> dict[str, object]:
    return {
        "phase1": {"mvp_weeks": PHASES["phase1"].estimate.mvp_weeks, "stable_weeks": PHASES["phase1"].estimate.stable_weeks},
        "phase2": {"mvp_weeks": PHASES["phase2"].estimate.mvp_weeks, "stable_weeks": PHASES["phase2"].estimate.stable_weeks},
        "phase3": {"mvp_weeks": PHASES["phase3"].estimate.mvp_weeks, "stable_weeks": PHASES["phase3"].estimate.stable_weeks},
        "full_ladder_target_weeks": FULL_LADDER_TARGET_WEEKS,
    }
