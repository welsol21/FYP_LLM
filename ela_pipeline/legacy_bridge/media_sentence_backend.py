"""Legacy media->sentence bridge using backend sentence-contract API semantics."""

from __future__ import annotations

from typing import Any, Callable

from ela_pipeline.client_storage import build_sentence_hash


SentenceContractProvider = Callable[[str, int], dict[str, Any]]


def _extract_sentence_text(row: dict[str, Any]) -> str:
    for key in ("sentence_text", "text", "text_eng"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def build_contract_rows_from_media_sentences(
    media_sentences: list[dict[str, Any]],
    *,
    sentence_contract_provider: SentenceContractProvider,
) -> list[dict[str, Any]]:
    """Convert media sentence stream into current contract rows via provider callback."""
    rows: list[dict[str, Any]] = []
    for fallback_idx, media_row in enumerate(media_sentences):
        sentence_idx = int(media_row.get("sentence_idx", fallback_idx))
        sentence_text = _extract_sentence_text(media_row)
        if not sentence_text:
            continue
        payload = sentence_contract_provider(sentence_text, sentence_idx)
        node = payload.get("sentence_node")
        if not isinstance(node, dict):
            raise ValueError("sentence_contract_provider must return dict with `sentence_node`")
        sentence_hash = str(payload.get("sentence_hash") or build_sentence_hash(sentence_text, sentence_idx))
        rows.append(
            {
                "sentence_idx": sentence_idx,
                "sentence_hash": sentence_hash,
                "sentence_node": node,
            }
        )
    rows.sort(key=lambda r: r["sentence_idx"])
    return rows

