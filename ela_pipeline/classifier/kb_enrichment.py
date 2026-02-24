"""spaCy-based enrichment for grammar KB examples."""

from __future__ import annotations

from typing import Any


def enrich_kb_example(text: str, nlp: Any) -> dict[str, Any]:
    doc = nlp(str(text or ""))
    tokens: list[dict[str, Any]] = []
    has_modal = False
    has_perfect_aux = False
    for token in doc:
        morph_dict: dict[str, str] = {}
        try:
            morph_dict = {k: "|".join(v) for k, v in token.morph.to_dict().items()}  # type: ignore[attr-defined]
        except Exception:
            morph_dict = {}
        row = {
            "text": token.text,
            "lemma": token.lemma_,
            "pos": token.pos_,
            "tag": token.tag_,
            "dep": token.dep_,
            "head_text": token.head.text,
            "head_i": int(token.head.i),
            "i": int(token.i),
            "morph": morph_dict,
        }
        tokens.append(row)
        if token.tag_ == "MD":
            has_modal = True
        if token.lemma_.lower() == "have" and token.dep_ in {"aux", "auxpass"}:
            has_perfect_aux = True

    derived = {
        "token_count": len(tokens),
        "has_modal_auxiliary": has_modal,
        "has_perfect_auxiliary": has_perfect_aux,
        "tam_signature": "modal_perfect_hint" if has_modal and has_perfect_aux else "unspecified",
    }

    return {
        "text": doc.text,
        "tokens": tokens,
        "derived_features": derived,
    }


def enrich_kb_examples(texts: list[str], nlp: Any) -> list[dict[str, Any]]:
    return [enrich_kb_example(text, nlp=nlp) for text in texts]
