"""Grammar knowledge-base helpers (banded curriculum seed)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class GrammarKBEntry:
    class_id: str
    cefr_level: str
    band: str
    blueprint_elementary: str
    blueprint_intermediate: str
    blueprint_advanced: str


def band_for_cefr(level: str) -> str:
    normalized = str(level or "").strip().upper()
    if normalized in {"A1", "A2"}:
        return "Elementary"
    if normalized in {"B1", "B2"}:
        return "Intermediate"
    if normalized in {"C1", "C2"}:
        return "Advanced"
    raise ValueError(f"Unsupported CEFR level for banding: {level!r}")


def build_seed_grammar_kb() -> list[GrammarKBEntry]:
    # Minimal deterministic seed from tense-table core to bootstrap classifier loops.
    rows: list[tuple[str, str, str, str, str]] = [
        ("tense_table::present_simple_active", "A1", "Present simple form and meaning.", "Present simple usage and agreement.", "Present simple constraints in discourse."),
        ("tense_table::past_simple_active", "A2", "Past simple form and meaning.", "Past simple in narrative sequence.", "Past simple interaction with aspect."),
        ("tense_table::present_perfect_active", "B1", "Present perfect core meaning.", "Present perfect vs past simple contrast.", "Present perfect pragmatic interpretation."),
        ("tense_table::past_perfect_active", "B2", "Past perfect background meaning.", "Past perfect for anterior events.", "Past perfect in layered timelines."),
        ("tense_table::modal_perfect", "C1", "Modal perfect basic form.", "Modal perfect epistemic interpretation.", "Modal perfect in stance and evidentiality."),
        ("tense_table::future_perfect_active", "C2", "Future perfect core form.", "Future perfect temporal projection.", "Future perfect for advanced rhetorical framing."),
    ]
    out: list[GrammarKBEntry] = []
    for class_id, level, e_text, i_text, a_text in rows:
        out.append(
            GrammarKBEntry(
                class_id=class_id,
                cefr_level=level,
                band=band_for_cefr(level),
                blueprint_elementary=e_text,
                blueprint_intermediate=i_text,
                blueprint_advanced=a_text,
            )
        )
    return out


def group_kb_by_band(entries: Iterable[GrammarKBEntry]) -> dict[str, list[GrammarKBEntry]]:
    grouped = {"Elementary": [], "Intermediate": [], "Advanced": []}
    for entry in entries:
        grouped.setdefault(entry.band, []).append(entry)
    return grouped
