"""Dual translation channel helpers (literary + idiomatic fallback)."""

from __future__ import annotations


def _rule_based_idiomatic_ru(text: str) -> str:
    out = text
    replacements = [
        ("необходимо", "нужно"),
        ("следует", "стоит"),
        ("должна была", "стоило бы"),
        ("должен был", "стоило бы"),
    ]
    for old, new in replacements:
        out = out.replace(old, new)
    return out


def build_dual_translation_channels(
    *,
    literary_text: str,
    target_lang: str,
) -> tuple[str, str]:
    """Return (literary, idiomatic) where idiomatic has deterministic fallback."""
    lit = (literary_text or "").strip()
    if not lit:
        return "", ""
    lang = (target_lang or "").strip().lower()
    if lang == "ru":
        idiomatic = _rule_based_idiomatic_ru(lit).strip()
    else:
        idiomatic = lit
    if not idiomatic:
        idiomatic = lit
    return lit, idiomatic
