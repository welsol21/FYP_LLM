"""Deterministic v3 filtering/normalization for rejected candidate diagnostics."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Tuple

DEFAULT_STOP_LIST = [
    r"sensibilisation",
    r"sensibilization",
    r"sensence",
    r"nod to",
    r"none\.?\s*node\s*content",
    r"\bnode\s*content\b",
    r"\bpersona\b",
    r"\bmust\b.*\buse\b",
    r"\bdoes not\b.*\buse\b",
]


@dataclass(frozen=True)
class RejectedCandidateFilterConfig:
    stop_list: Sequence[str] = field(default_factory=lambda: DEFAULT_STOP_LIST)
    allowlist_sentence_templates: Sequence[str] = field(default_factory=list)
    allowlist_short_tokens: Sequence[str] = field(default_factory=list)
    min_len: int = 5
    use_nfkc_normalization: bool = True


DEFAULT_REJECTED_CANDIDATE_FILTER_CONFIG = RejectedCandidateFilterConfig()


def _normalize_quotes(text: str) -> str:
    table = {
        ord("“"): '"',
        ord("”"): '"',
        ord("‘"): "'",
        ord("’"): "'",
    }
    return text.translate(table)


def normalize_candidate_text(text: str, *, use_nfkc: bool = True) -> str:
    out = text or ""
    if use_nfkc:
        out = unicodedata.normalize("NFKC", out)
    out = _normalize_quotes(out)
    out = " ".join(out.strip().split())
    out = re.sub(r"\s+([.,:;!?])", r"\1", out)
    out = re.sub(r"\.{2,}", ".", out)
    out = re.sub(r"\s*([.,:;!?])\s*$", r"\1", out)
    out = re.sub(r"[.\s]+$", ".", out) if out.endswith(".") or out.endswith(" ") else out
    out = out.strip()
    return out


def norm_key(text: str, *, use_nfkc: bool = True) -> str:
    out = normalize_candidate_text(text, use_nfkc=use_nfkc)
    out = re.sub(r"[.\s]+$", "", out)
    return out.lower()


def _is_sentence_prefixed(text: str) -> bool:
    return bool(re.match(r"^\s*sentence\s*:", text, flags=re.IGNORECASE))


def _matches_stop_list(text: str, stop_list: Sequence[str]) -> bool:
    for pattern in stop_list:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return True
    return False


def keep_candidate(
    text: str,
    config: RejectedCandidateFilterConfig = DEFAULT_REJECTED_CANDIDATE_FILTER_CONFIG,
) -> bool:
    normalized = normalize_candidate_text(text, use_nfkc=config.use_nfkc_normalization)
    if not normalized:
        return False

    key = norm_key(normalized, use_nfkc=False)
    if _matches_stop_list(normalized, config.stop_list):
        return False

    if _is_sentence_prefixed(normalized):
        if key not in {k.lower() for k in config.allowlist_sentence_templates}:
            return False

    if len(normalized.strip()) < config.min_len and key not in {k.lower() for k in config.allowlist_short_tokens}:
        return False

    return True


def normalize_and_aggregate_rejected_candidates(
    rejected_candidates: Sequence[str] | None = None,
    rejected_items: Sequence[Dict[str, str]] | None = None,
    config: RejectedCandidateFilterConfig = DEFAULT_REJECTED_CANDIDATE_FILTER_CONFIG,
) -> Tuple[List[str], List[Dict[str, object]]]:
    allow_sentence_keys = {k.lower() for k in config.allowlist_sentence_templates}
    allow_short_keys = {k.lower() for k in config.allowlist_short_tokens}
    local_config = RejectedCandidateFilterConfig(
        stop_list=config.stop_list,
        allowlist_sentence_templates=allow_sentence_keys,
        allowlist_short_tokens=allow_short_keys,
        min_len=config.min_len,
        use_nfkc_normalization=config.use_nfkc_normalization,
    )

    grouped: Dict[str, Dict[str, object]] = {}
    order: List[str] = []

    def upsert(raw_text: str, reason: str | None, count_delta: int) -> None:
        if not keep_candidate(raw_text, config=local_config):
            return
        normalized = normalize_candidate_text(raw_text, use_nfkc=local_config.use_nfkc_normalization)
        key = norm_key(normalized, use_nfkc=False)
        if key not in grouped:
            grouped[key] = {"text": normalized, "count": 0, "reasons": set()}
            order.append(key)
        grouped[key]["count"] = int(grouped[key]["count"]) + max(0, int(count_delta))
        if reason:
            grouped[key]["reasons"].add(str(reason))

    for item in rejected_candidates or []:
        if isinstance(item, str):
            upsert(item, None, 1)

    for item in rejected_items or []:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if not isinstance(text, str):
            continue
        reason = item.get("reason")
        count = item.get("count", 1)
        if not isinstance(count, int):
            count = 1
        upsert(text, reason if isinstance(reason, str) else None, count)

    clean_candidates: List[str] = []
    clean_stats: List[Dict[str, object]] = []
    for key in order:
        item = grouped[key]
        clean_candidates.append(item["text"])
        clean_stats.append(
            {
                "text": item["text"],
                "count": int(item["count"]),
                "reasons": sorted(item["reasons"]),
            }
        )
    return clean_candidates, clean_stats
