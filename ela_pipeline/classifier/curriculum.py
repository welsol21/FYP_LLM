"""Curriculum helpers for per-class CEFR ladder enforcement."""

from __future__ import annotations

from dataclasses import dataclass

CEFR_LADDER = ("A1", "A2", "B1", "B2", "C1", "C2")


@dataclass(frozen=True)
class LadderValidationIssue:
    class_id: str
    message: str


def validate_per_class_cefr_ladder(per_class_ladder: dict[str, list[str]]) -> list[LadderValidationIssue]:
    issues: list[LadderValidationIssue] = []
    if not isinstance(per_class_ladder, dict):
        return [LadderValidationIssue(class_id="$", message="per_class_cefr_ladder must be object")]

    required = set(CEFR_LADDER)
    for class_id, levels in per_class_ladder.items():
        cid = str(class_id or "").strip()
        if not cid:
            issues.append(LadderValidationIssue(class_id="$", message="class_id must be non-empty"))
            continue
        if not isinstance(levels, list):
            issues.append(LadderValidationIssue(class_id=cid, message="ladder must be list"))
            continue
        normalized = [str(v or "").strip().upper() for v in levels]
        level_set = set(normalized)
        unknown = [lvl for lvl in normalized if lvl and lvl not in required]
        if unknown:
            issues.append(
                LadderValidationIssue(
                    class_id=cid,
                    message=f"unknown CEFR levels: {sorted(set(unknown))}",
                )
            )
        missing = [lvl for lvl in CEFR_LADDER if lvl not in level_set]
        if missing:
            issues.append(
                LadderValidationIssue(
                    class_id=cid,
                    message=f"missing required levels: {missing}",
                )
            )
        # Sequence check (non-decreasing over canonical ladder index).
        idx_map = {lvl: i for i, lvl in enumerate(CEFR_LADDER)}
        filtered = [lvl for lvl in normalized if lvl in idx_map]
        for i in range(1, len(filtered)):
            if idx_map[filtered[i]] < idx_map[filtered[i - 1]]:
                issues.append(
                    LadderValidationIssue(
                        class_id=cid,
                        message="levels must follow non-decreasing CEFR order",
                    )
                )
                break
    return issues
