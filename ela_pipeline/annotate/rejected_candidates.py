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
    r"\bnode\s*type\b",
    r"\bpart\s+of\s+speech\b",
    r"\bpersona\b",
    r"\bsensational\b",
    r"\bsensibilite\b",
    r"\bsensibilit[aä]t\b",
    r"\bin\s+english\b",
    r"\bnatural\s+english\b",
    r"\bbooleans?\b",
    r"\bjson\s+fragments?\b",
    r"\bplaceholders?\b",
    r"\bnode,\s*label\b",
    r"\bsentence\s*:",
    r"\bsensitence\b",
    r"\benglish\b.*\bfrench\b",
    r"\bacademic\s+and\s+professional\s+development\b",
    r"\bnode\s*[:;]",
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


def _is_sentence_like_meta(text: str) -> bool:
    return bool(re.match(r"^\s*senten(?:ce|se)\b", text, flags=re.IGNORECASE))


def _matches_stop_list(text: str, stop_list: Sequence[str]) -> bool:
    for pattern in stop_list:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return True
    return False


def _fails_repetition_quality(text: str) -> bool:
    tokens = re.findall(r"[a-zA-Z']+", text.lower())
    token_count = len(tokens)
    if token_count < 10:
        return False

    unique_ratio = len(set(tokens)) / token_count
    if unique_ratio < 0.45:
        return True

    counts: Dict[str, int] = {}
    for tok in tokens:
        counts[tok] = counts.get(tok, 0) + 1

    spam_terms = {"noun", "verb", "phrase", "sentence", "clause", "word"}
    spam_hits = sum(counts.get(t, 0) for t in spam_terms)
    if spam_hits / token_count > 0.35:
        return True

    return False


def _fails_label_spam(text: str) -> bool:
    lowered = text.lower()
    matches = re.findall(r"\b(node|form|tense|word|pos|type)\s*[:;]", lowered)
    return len(matches) >= 3


def _is_temporal_before_after_phrase(node_part_of_speech: str | None, node_content: str | None) -> bool:
    pos = (node_part_of_speech or "").strip().lower()
    if pos != "prepositional phrase":
        return False
    content = (node_content or "").strip().lower()
    return content.startswith("before ") or content.startswith("after ")


def fails_semantic_sanity(
    candidate_text: str,
    *,
    node_type: str | None = None,
    node_part_of_speech: str | None = None,
    node_content: str | None = None,
) -> bool:
    text = candidate_text.lower()
    node_type_l = (node_type or "").strip().lower()
    if node_type_l in {"word", "phrase"} and "subordinate clause" in text:
        return True
    if _is_temporal_before_after_phrase(node_part_of_speech, node_content):
        if "concession" in text or "reason" in text:
            return True
    return False


def keep_candidate(
    text: str,
    config: RejectedCandidateFilterConfig = DEFAULT_REJECTED_CANDIDATE_FILTER_CONFIG,
    *,
    node_type: str | None = None,
    node_part_of_speech: str | None = None,
    node_content: str | None = None,
) -> bool:
    normalized = normalize_candidate_text(text, use_nfkc=config.use_nfkc_normalization)
    if not normalized:
        return False

    key = norm_key(normalized, use_nfkc=False)
    allow_sentence_keys = {k.lower() for k in config.allowlist_sentence_templates}
    is_allowlisted_sentence_template = bool(
        re.match(r"^\s*sentence\s*:", normalized, flags=re.IGNORECASE) and key in allow_sentence_keys
    )

    if _matches_stop_list(normalized, config.stop_list) and not is_allowlisted_sentence_template:
        return False

    if _fails_repetition_quality(normalized):
        return False

    if _fails_label_spam(normalized):
        return False

    if _is_sentence_like_meta(normalized):
        if key not in allow_sentence_keys:
            return False

    if len(normalized.strip()) < config.min_len and key not in {k.lower() for k in config.allowlist_short_tokens}:
        return False

    if fails_semantic_sanity(
        normalized,
        node_type=node_type,
        node_part_of_speech=node_part_of_speech,
        node_content=node_content,
    ):
        return False

    return True


def normalize_and_aggregate_rejected_candidates(
    rejected_candidates: Sequence[str] | None = None,
    rejected_items: Sequence[Dict[str, str]] | None = None,
    config: RejectedCandidateFilterConfig = DEFAULT_REJECTED_CANDIDATE_FILTER_CONFIG,
    *,
    node_type: str | None = None,
    node_part_of_speech: str | None = None,
    node_content: str | None = None,
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
        if not keep_candidate(
            raw_text,
            config=local_config,
            node_type=node_type,
            node_part_of_speech=node_part_of_speech,
            node_content=node_content,
        ):
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
