"""Generic parser-backed sentence enrichment for corpus sentence rows."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import spacy


_PARSER_ENGINE = "spacy"
_PARSER_MODEL = "en_core_web_sm"


@lru_cache(maxsize=1)
def _load_parser():
    return spacy.load(_PARSER_MODEL, disable=["ner"])


def _token_row(token) -> dict[str, Any]:
    morph = token.morph.to_dict() if token.morph else {}
    dep = str(token.dep_ or "").strip()
    return {
        "id": int(token.i + 1),
        "text": token.text,
        "lemma": token.lemma_,
        "upos": token.pos_,
        "xpos": token.tag_,
        "morph": morph,
        "head": 0 if token.head == token else int(token.head.i + 1),
        "dep": dep.lower(),
    }


def enrich_sentence_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return []

    nlp = _load_parser()
    texts = [str(row.get("text") or "").strip() for row in rows]
    docs = list(nlp.pipe(texts))

    out: list[dict[str, Any]] = []
    for row, doc in zip(rows, docs):
        provenance = dict(row.get("provenance") or {})
        provenance["parser_engine"] = _PARSER_ENGINE
        provenance["parser_model"] = _PARSER_MODEL
        out.append(
            {
                **row,
                "tokens": [_token_row(token) for token in doc],
                "provenance": provenance,
            }
        )
    return out
