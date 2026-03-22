"""Build book-derived Word notation rows from rulebook-style reference books."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from ela_pipeline.annotate.note_context import build_note_context_prompt
from ela_pipeline.dataset.build_dataset import PROMPT_TEMPLATE_VERSION, _build_template_target
from ela_pipeline.dataset.build_reference_word_synthetic_corpus import (
    WORD_REFERENCE_ANCHORS,
    WORD_TOPIC_TO_TEMPLATE_IDS,
    _clean,
    _extract_explicit_contexts,
    _looks_like_context_material,
    _split_template_target,
    _topic_template_match_is_strict,
    _word_template_features,
)
from ela_pipeline.dataset.build_rulebook_note_context_pairs import (
    _EXPLANATION_HINTS,
    _extract_source_first_examples,
    _line_slice,
    _norm,
)
from ela_pipeline.parse.spacy_parser import load_nlp
from ela_pipeline.skeleton.builder import build_skeleton


_CONTROL_GLYPH_RE = re.compile(r"[\x00-\x1f\uF000-\uF8FF]")
_WS_RE = re.compile(r"\s+")
_INCOMPLETE_LAST_WORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "by",
    "for",
    "from",
    "if",
    "in",
    "of",
    "on",
    "or",
    "than",
    "that",
    "the",
    "to",
    "with",
}
_WORD_META_CONTEXT_RE = re.compile(
    r"\b(?:adjective|adjectives|article|articles|choice|clause|clauses|common nouns?|context|"
    r"determiner|determiners|form|forms|grammar|noun phrase|nouns?|phrase|phrases|pronouns?|"
    r"reference|referent|term|terms|topic|usage|verb phrase|verbs?)\b",
    re.IGNORECASE,
)
_WORD_BANNED_SENTENCE_START_RE = re.compile(
    r"^(?:this|these|those|a|an|the|many|most|such|common|typical)\b",
    re.IGNORECASE,
)


def _iter_jsonl(path: str):
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def _write_json(path: str, payload: dict[str, Any]) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: str, rows: list[dict[str, Any]]) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _normalize_payload_lines(path: str) -> list[str]:
    text = Path(path).read_text(encoding="utf-8")
    text = str(text or "").replace("\r\n", "\n").replace("\r", "\n").replace("\f", "\n")
    return [_norm(line) for line in text.split("\n")]


def _walk_words(
    node: dict[str, Any],
    *,
    parent: dict[str, Any] | None = None,
    path_types: list[str] | None = None,
    depth: int = 0,
):
    current_path = list(path_types or [])
    current_type = str(node.get("type") or "").strip()
    if current_type:
        current_path.append(current_type)
    children = [child for child in (node.get("linguistic_elements") or []) if isinstance(child, dict)]
    total = len(children)
    for index, child in enumerate(children):
        child_type = str(child.get("type") or "").strip()
        child_path = list(current_path)
        if child_type:
            child_path.append(child_type)
        if child_type == "Word":
            yield child, node, child_path, depth + 1, index, max(1, total)
        yield from _walk_words(child, parent=node, path_types=current_path, depth=depth + 1)


def _looks_clean_word_context(text: str) -> bool:
    cleaned = _clean(text)
    words = re.findall(r"[A-Za-z']+", cleaned)
    if len(words) < 3:
        return False
    if cleaned.endswith((",", ";", ":")):
        return False
    if cleaned[:1] in {",", ";", ":", ")"} or cleaned.startswith("("):
        return False
    if re.search(r"\b(?:see(?:\s+also|\s+further\s+under)?|compare|cf\.?|section\s+\d+|glossary|dictionary)\b", cleaned, re.IGNORECASE):
        return False
    if words and words[-1].lower() in _INCOMPLETE_LAST_WORDS:
        return False
    return True


def _looks_preposition_phrase_context(text: str, nlp: Any) -> bool:
    cleaned = _clean(text)
    words = re.findall(r"[A-Za-z']+", cleaned)
    if not (2 <= len(words) <= 8):
        return False
    doc = nlp(cleaned)
    tokens = [token for token in doc if not token.is_space]
    if not tokens:
        return False
    if tokens[0].pos_ != "ADP":
        return False
    return any(token.pos_ in {"DET", "ADJ", "NOUN", "PROPN", "PRON", "NUM"} for token in tokens[1:])


def _looks_word_sentence_context(text: str, nlp: Any) -> bool:
    cleaned = _clean(text)
    if not _looks_like_context_material(cleaned, nlp):
        return False
    if _WORD_BANNED_SENTENCE_START_RE.search(cleaned) and _WORD_META_CONTEXT_RE.search(cleaned):
        return False
    return True


def _topic_keys_for_row(row: dict[str, Any]) -> list[str]:
    haystack = f"{row.get('entry_head') or ''} {row.get('heading') or ''} {row.get('text') or ''}".lower()
    topic_keys: list[str] = []
    for topic_key, anchors in WORD_REFERENCE_ANCHORS.items():
        if any(anchor in haystack for anchor in anchors):
            topic_keys.append(topic_key)
    return topic_keys


def _extract_notation_text(row: dict[str, Any], nlp: Any) -> str:
    text = _norm(row.get("text") or "")
    if not text:
        return ""
    doc = nlp(text)
    kept: list[str] = []
    for sent in doc.sents:
        sent_text = _norm(sent.text)
        if len(re.findall(r"[A-Za-z]{2,}", sent_text)) < 5:
            continue
        lowered = sent_text.lower()
        if any(hint in lowered for hint in _EXPLANATION_HINTS):
            kept.append(sent_text)
        if len(kept) >= 2:
            break
    if kept:
        return _norm(" ".join(kept))
    return text[:240].strip()


def build_rulebook_word_notation_rows(
    *,
    rulebook_jsonl: str,
    payload_txt: str,
    spacy_model: str = "en_core_web_sm",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    nlp = load_nlp(spacy_model)
    payload_lines = _normalize_payload_lines(payload_txt)
    rows = list(_iter_jsonl(rulebook_jsonl))

    out_rows: list[dict[str, Any]] = []
    stats: dict[str, int] = {
        "rows_seen": len(rows),
        "rows_with_word_topic": 0,
        "contexts_found": 0,
        "contracts_built": 0,
        "rows_emitted": 0,
    }

    for row in rows:
        row_type = str(row.get("row_type") or "")
        if row_type != "dictionary_entry":
            continue
        topic_keys = _topic_keys_for_row(row)
        if not topic_keys:
            continue
        stats["rows_with_word_topic"] += 1
        notation_text = _extract_notation_text(row, nlp)
        if not notation_text:
            continue

        entry_head = _norm(row.get("entry_head") or row.get("heading"))
        lines = _line_slice(payload_lines, int(row.get("line_start") or 0), int(row.get("line_end") or 0))
        contexts = _extract_explicit_contexts(str(row.get("text") or ""), nlp)
        if lines:
            contexts.extend(_extract_source_first_examples(lines, entry_head, nlp))
        deduped_contexts: list[str] = []
        seen_contexts: set[str] = set()
        for context in contexts:
            cleaned = _clean(context)
            if not cleaned:
                continue
            if not _looks_clean_word_context(cleaned):
                continue
            if not (_looks_word_sentence_context(cleaned, nlp) or ("word_preposition" in topic_keys and _looks_preposition_phrase_context(cleaned, nlp))):
                continue
            key = cleaned.lower()
            if key in seen_contexts:
                continue
            seen_contexts.add(key)
            deduped_contexts.append(cleaned)
        if not deduped_contexts:
            continue
        stats["contexts_found"] += len(deduped_contexts)

        for context_text in deduped_contexts[:5]:
            try:
                contract_doc = build_skeleton(context_text, nlp)
            except Exception:
                continue
            if not contract_doc:
                continue
            stats["contracts_built"] += 1
            for sentence_text, sentence_node in contract_doc.items():
                for node, parent, path_types, depth, sibling_index, sibling_count in _walk_words(sentence_node, path_types=[]):
                    word_text = _norm(node.get("content"))
                    if not word_text:
                        continue
                    features = _word_template_features(node)
                    tam_bucket = str(node.get("tam_construction") or "none").strip().lower() or "none"
                    target, _ = _build_template_target("Word", word_text, features, tam_bucket)
                    if not target:
                        continue
                    template_id, synthetic_target = _split_template_target(target)
                    matched_topic = None
                    for topic_key in topic_keys:
                        if template_id not in WORD_TOPIC_TO_TEMPLATE_IDS.get(topic_key, set()):
                            continue
                        if _topic_template_match_is_strict(
                            topic_key=topic_key,
                            template_id=template_id,
                            word_text=word_text,
                            features=features,
                        ):
                            matched_topic = topic_key
                            break
                    if not matched_topic:
                        continue
                    if template_id == "WORD_PREPOSITION" and word_text[:1].isupper():
                        continue
                    if template_id == "WORD_NOUN_COMMON" and (
                        word_text.isupper() or (word_text[:1].isupper() and len(re.findall(r"[A-Za-z']+", context_text)) <= 8)
                    ):
                        continue
                    prompt = build_note_context_prompt(
                        node=node,
                        parent=parent,
                        sentence_node=sentence_node,
                        path_types=path_types,
                        depth=depth,
                        sibling_index=sibling_index,
                        sibling_count=sibling_count,
                        template_version=PROMPT_TEMPLATE_VERSION,
                    )
                    out_rows.append(
                        {
                            "input": prompt,
                            "target": synthetic_target,
                            "book_notation_text": notation_text,
                            "level": "Word",
                            "task": "linguistic_note",
                            "prompt_template_version": PROMPT_TEMPLATE_VERSION,
                            "template_id": template_id,
                            "topic_key": matched_topic,
                            "word_text": word_text,
                            "sentence_text": sentence_text,
                            "context_text": context_text,
                            "heading": row.get("heading"),
                            "entry_head": row.get("entry_head"),
                            "row_type": row_type,
                            "source_path": row.get("source_path"),
                        }
                    )
                    stats["rows_emitted"] += 1

    report = {
        "pipeline_version": "rulebook_word_notation_v1",
        "rulebook_jsonl": str(Path(rulebook_jsonl).resolve()),
        "payload_txt": str(Path(payload_txt).resolve()),
        "spacy_model": spacy_model,
        "stats": stats,
        "template_counts": {
            key: sum(1 for row in out_rows if row.get("template_id") == key)
            for key in sorted({str(row.get("template_id") or "") for row in out_rows})
        },
        "topic_counts": {
            key: sum(1 for row in out_rows if row.get("topic_key") == key)
            for key in sorted({str(row.get("topic_key") or "") for row in out_rows})
        },
    }
    return out_rows, report


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Word-level book notation rows from rulebook books.")
    parser.add_argument("--rulebook-jsonl", required=True)
    parser.add_argument("--payload-txt", required=True)
    parser.add_argument("--output-jsonl", required=True)
    parser.add_argument("--report-json", required=True)
    parser.add_argument("--spacy-model", default="en_core_web_sm")
    args = parser.parse_args()

    rows, report = build_rulebook_word_notation_rows(
        rulebook_jsonl=args.rulebook_jsonl,
        payload_txt=args.payload_txt,
        spacy_model=args.spacy_model,
    )
    _write_jsonl(args.output_jsonl, rows)
    _write_json(args.report_json, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
