"""Deterministic filtering/normalization for rejected candidates diagnostics."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Sequence, Tuple

TAIL_PUNCTUATION_CHARS = ".,;:—-…"

DEFAULT_REJECT_STOP_SUBSTRINGS = [
    "sensibilisation",
    "sensibilization",
    "sensence",
    "sensense",
    "sensibilisation:",
    "sensibilization:",
    "node content:",
    "node content .",
    "node content.",
    "node type",
    "part of speech",
    "pos:",
    "none. node content",
    "none node content",
    "nod to",
    "is a nod to",
    "is a nod",
    "nod used",
    "sentence to the subject",
    "sentence is a nod",
    "sentence in her instincts",
    "gives rise to the same underlying situation",
    "underlying situation",
    "to the subject",
    "subject of the clause",
]

DEFAULT_REJECT_REGEX_PATTERNS = [
    r"^sentence\s*:\s*.+$",
    r"^node\s+content\b.*$",
    r"^node\s+type\b.*$",
    r"^part\s+of\s+speech\b.*$",
    r"^node\s+content\.\s*part\s+of\s+speech\.?$",
    r"^node\s+content\.\s*part\s+of\s+speech\s+.+$",
    r".*\b(null|none)\b.*\bnode\s+content\b.*",
    r".*\bsensibilis(a|z)tion\b.*",
    r".*\bsensence\b.*",
    r".*\bnod\s+to\b.*",
    r".*\bis\s+a\s+nod\b.*",
    r".*\bsentence\s+to\s+the\s+subject\b.*",
    r".*\bgives\s+rise\s+to\s+the\s+same\s+underlying\s+situation\b.*",
    r"^\s*$",
]

DEFAULT_SENTENCE_PREFIX_WHITELIST_PATTERNS = [
    r"^sentence\s*:\s*<sentence>$",
    r"^sentence\s*:\s*\{sentence\}$",
    r"^sentence\s*:\s*\[sentence\]$",
]


@dataclass(frozen=True)
class RejectedCandidateFilterConfig:
    reject_stop_substrings: Sequence[str] = field(default_factory=lambda: DEFAULT_REJECT_STOP_SUBSTRINGS)
    reject_regex_patterns: Sequence[str] = field(default_factory=lambda: DEFAULT_REJECT_REGEX_PATTERNS)
    allow_sentence_prefix_candidates: bool = False
    sentence_prefix_whitelist_patterns: Sequence[str] = field(
        default_factory=lambda: DEFAULT_SENTENCE_PREFIX_WHITELIST_PATTERNS
    )
    min_candidate_length: int = 8
    max_candidate_length: int = 220
    max_nonalpha_ratio: float = 0.35
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


def _trim_tail_punctuation(text: str) -> str:
    while text and text[-1] in TAIL_PUNCTUATION_CHARS:
        text = text[:-1].rstrip()
    return text


def _collapse_duplicate_dots(text: str) -> str:
    return re.sub(r"(?<!\d)\.{2,}(?!\d)", ".", text)


def normalize_candidate_text(text: str, *, use_nfkc: bool = True) -> str:
    normalized = text or ""
    if use_nfkc:
        normalized = unicodedata.normalize("NFKC", normalized)
    normalized = _normalize_quotes(normalized)
    normalized = " ".join(normalized.strip().split())
    normalized = _collapse_duplicate_dots(normalized)
    normalized = _trim_tail_punctuation(normalized)
    return normalized


def _dedup_key(text: str) -> str:
    return text.lower()


def _is_sentence_prefixed(text: str) -> bool:
    return bool(re.match(r"^sentence\s*:", text, flags=re.IGNORECASE))


def _is_sentence_prefix_allowed(text: str, whitelist_patterns: Sequence[str]) -> bool:
    for pattern in whitelist_patterns:
        if re.match(pattern, text, flags=re.IGNORECASE):
            return True
    return False


def _nonalpha_ratio(text: str) -> float:
    chars = [ch for ch in text if not ch.isspace()]
    if not chars:
        return 1.0
    nonalpha = sum(1 for ch in chars if not ch.isalpha())
    return nonalpha / len(chars)


def is_rejected_candidate_noise(
    text: str,
    config: RejectedCandidateFilterConfig = DEFAULT_REJECTED_CANDIDATE_FILTER_CONFIG,
) -> bool:
    if not text:
        return True

    primary = " ".join(text.strip().split())
    if not primary:
        return True

    primary_l = primary.lower()
    for fragment in config.reject_stop_substrings:
        if fragment.lower() in primary_l:
            return True

    sentence_prefixed = _is_sentence_prefixed(primary)
    sentence_whitelisted = sentence_prefixed and _is_sentence_prefix_allowed(
        primary, config.sentence_prefix_whitelist_patterns
    )
    for pattern in config.reject_regex_patterns:
        if sentence_whitelisted and pattern == r"^sentence\s*:\s*.+$":
            continue
        if re.match(pattern, primary, flags=re.IGNORECASE):
            return True

    if sentence_prefixed:
        if not config.allow_sentence_prefix_candidates:
            return True
        if not sentence_whitelisted:
            return True

    normalized = normalize_candidate_text(primary, use_nfkc=config.use_nfkc_normalization)
    if len(normalized) < config.min_candidate_length:
        return True
    if len(normalized) > config.max_candidate_length and (":" in normalized or _is_sentence_prefixed(normalized)):
        return True
    if _nonalpha_ratio(normalized) > config.max_nonalpha_ratio:
        return True
    if "::" in normalized:
        return True
    if len(re.findall(r"node\s+content\s*:", normalized, flags=re.IGNORECASE)) >= 2:
        return True

    return False


def _pick_human_readable(candidates: Sequence[str]) -> str:
    def score(text: str) -> Tuple[int, int, int, str]:
        return (
            len(text),
            text.count(":"),
            text.count('"') + text.count("'"),
            text.lower(),
        )

    return sorted(candidates, key=score)[0]


def normalize_and_aggregate_rejected_candidates(
    rejected_candidates: Sequence[str] | None = None,
    rejected_items: Sequence[Dict[str, str]] | None = None,
    config: RejectedCandidateFilterConfig = DEFAULT_REJECTED_CANDIDATE_FILTER_CONFIG,
) -> Tuple[List[str], List[Dict[str, object]]]:
    grouped: Dict[str, Dict[str, object]] = {}

    def upsert(raw_text: str, reason: str | None, count_delta: int) -> None:
        if is_rejected_candidate_noise(raw_text, config=config):
            return
        canonical = normalize_candidate_text(raw_text, use_nfkc=config.use_nfkc_normalization)
        if not canonical:
            return
        key = _dedup_key(canonical)
        if key not in grouped:
            grouped[key] = {"texts": [], "count": 0, "reasons": set()}
        grouped[key]["texts"].append(canonical)
        grouped[key]["count"] = int(grouped[key]["count"]) + int(max(0, count_delta))
        if reason:
            grouped[key]["reasons"].add(str(reason))

    for text in rejected_candidates or []:
        if isinstance(text, str):
            upsert(text, None, 1)

    for item in rejected_items or []:
        if not isinstance(item, dict):
            continue
        raw_text = item.get("text")
        if not isinstance(raw_text, str):
            continue
        reason = item.get("reason")
        count_delta = item.get("count", 1)
        if not isinstance(count_delta, int):
            count_delta = 1
        upsert(raw_text, reason if isinstance(reason, str) else None, count_delta)

    stats: List[Dict[str, object]] = []
    for key in sorted(grouped.keys()):
        entry = grouped[key]
        readable = _pick_human_readable(entry["texts"])
        stats.append(
            {
                "text": readable,
                "count": int(entry["count"]),
                "reasons": sorted(entry["reasons"]),
            }
        )

    deduped = [item["text"] for item in stats]
    return deduped, stats
