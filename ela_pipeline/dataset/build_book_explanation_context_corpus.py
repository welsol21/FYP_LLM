"""Build a note-context corpus from extracted grammar-book snippets.

Pipeline:
1. Read author-explanation snippets extracted from books.
2. Split snippets into explanation/context pairs.
3. Build a contract for each context text.
4. Attach contract-template payloads to nodes and add book-derived templated
   notes where the book topic is compatible with the node template family.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from ela_pipeline.annotate.contract_template_builder import build_contract_template_payload
from ela_pipeline.dataset.template_topic_mapping import topic_to_template_id
from ela_pipeline.parse.spacy_parser import load_nlp
from ela_pipeline.skeleton.builder import build_skeleton

EXAMPLE_MARKERS = (
    "for example",
    "for instance",
    "example:",
    "examples:",
    "e.g.",
    "such as",
    "compare:",
)
PEDAGOGICAL_HINTS = (
    "used",
    "use ",
    "means",
    "refers",
    "shows",
    "expresses",
    "indicates",
    "introduces",
    "modifies",
    "describes",
    "called",
    "pattern",
    "structure",
    "clause",
    "phrase",
    "sentence",
    "question tag",
    "relative clause",
    "preposition",
    "passive",
    "conditional",
)
QUOTED_EXAMPLE_RE = re.compile(r"[\"“'`](.{8,}?)['\"”`]")
DOT_LEADER_RE = re.compile(r"\.{4,}")
CONTROL_GLYPH_RE = re.compile(r"[\x00-\x1f\uF000-\uF8FF]")
SECTION_REF_RE = re.compile(r"(?:^|\s)\d+(?:\.\d+){1,}(?:\s|$)")
TRAILING_NOTE_RE = re.compile(r"(\(cf\..*$|\[i\.e\..*$|\[cf\..*$|>\s.*$)", re.IGNORECASE)
INCOMPLETE_ENDINGS = {
    "or",
    "and",
    "to",
    "of",
    "in",
    "with",
    "for",
    "on",
    "at",
    "by",
    "than",
    "that",
    "which",
    "who",
    "whom",
    "whose",
    "when",
    "where",
    "if",
    "whether",
    "as",
    "because",
    "rather",
    "like",
}
META_CONTEXT_PREFIXES = (
    "compare ",
    "see ",
    "cf.",
    "cf ",
    "formulaically ",
    "derivational",
    "inflectional",
    "defined as",
    "definition",
    "term ",
    "terms ",
)


def _norm(value: Any) -> str:
    value = CONTROL_GLYPH_RE.sub(" ", str(value or ""))
    return " ".join(value.strip().split())


def _clean_candidate_text(text: str) -> str:
    text = _norm(text).replace("*", "")
    text = TRAILING_NOTE_RE.sub("", text).strip()
    text = text.rstrip("([")
    text = re.sub(r"\s+\)", ")", text)
    return _norm(text)


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


def _row_id(row: dict[str, Any], explanation_text: str, context_text: str) -> str:
    digest = hashlib.sha1(
        json.dumps(
            {
                "source_path": row.get("source_path"),
                "heading": row.get("heading"),
                "topic_key": row.get("topic_key"),
                "explanation_text": explanation_text,
                "context_text": context_text,
            },
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()[:12]
    return f"book_note_context_{digest}"


def _split_sentences(text: str, nlp: Any) -> list[str]:
    doc = nlp(str(text or ""))
    sentences = [_norm(sent.text) for sent in doc.sents]
    return [sent for sent in sentences if _looks_like_usable_text(sent, require_sentence=False)]


def _looks_like_usable_text(text: str, *, require_sentence: bool) -> bool:
    text = _norm(text)
    if not text:
        return False
    if DOT_LEADER_RE.search(text):
        return False
    if len(SECTION_REF_RE.findall(text)) >= 2:
        return False
    alpha_words = re.findall(r"[A-Za-z]{2,}", text)
    if len(alpha_words) < 4:
        return False
    digit_count = sum(ch.isdigit() for ch in text)
    alpha_count = sum(ch.isalpha() for ch in text)
    if digit_count > max(3, alpha_count // 3):
        return False
    if require_sentence and len(alpha_words) < 5:
        return False
    return True


def _has_predicate(text: str, nlp: Any) -> bool:
    doc = nlp(text)
    return any(token.pos_ in {"VERB", "AUX"} for token in doc)


def _has_subject(text: str, nlp: Any) -> bool:
    doc = nlp(text)
    return any(token.dep_ in {"nsubj", "nsubjpass", "expl", "csubj"} for token in doc)


def _starts_like_example_clause(text: str, nlp: Any) -> bool:
    doc = nlp(text)
    tokens = [token for token in doc if not token.is_space]
    if not tokens:
        return False
    first = tokens[0]
    if first.text[:1].isupper():
        return True
    if first.lower_ in {"it", "there", "he", "she", "they", "we", "i", "you", "who", "what", "when", "where", "why", "how"}:
        return True
    if first.pos_ in {"PRON", "PROPN", "DET", "NOUN"}:
        return True
    return False


def _ends_incomplete(text: str) -> bool:
    words = re.findall(r"[A-Za-z']+", text.lower())
    return bool(words and words[-1] in INCOMPLETE_ENDINGS)


def _looks_like_context_material(text: str, nlp: Any) -> bool:
    text = _clean_candidate_text(text)
    if not _looks_like_usable_text(text, require_sentence=False):
        return False
    lowered = text.lower()
    if lowered.startswith(META_CONTEXT_PREFIXES):
        return False
    if any(marker in lowered for marker in PEDAGOGICAL_HINTS):
        return False
    if text.endswith((":",";")):
        return False
    if _ends_incomplete(text):
        return False
    if not _has_predicate(text, nlp):
        return False
    if not _has_subject(text, nlp):
        return False
    return True


def _looks_like_neighbor_context(text: str, nlp: Any) -> bool:
    text = _clean_candidate_text(text)
    if not _looks_like_context_material(text, nlp):
        return False
    return _starts_like_example_clause(text, nlp)


def _extract_explicit_contexts(text: str, nlp: Any) -> list[str]:
    contexts: list[str] = []
    text_norm = str(text or "")
    for match in QUOTED_EXAMPLE_RE.finditer(text_norm):
        candidate = _clean_candidate_text(match.group(1))
        if _looks_like_context_material(candidate, nlp):
            contexts.append(candidate)
    lowered = text_norm.lower()
    for marker in EXAMPLE_MARKERS:
        idx = lowered.find(marker)
        if idx < 0:
            continue
        tail = _norm(text_norm[idx + len(marker) :].lstrip(" :-,"))
        for part in re.split(r"[:;•]|(?<=\.)\s+", tail):
            candidate = _clean_candidate_text(part)
            if _looks_like_context_material(candidate, nlp):
                contexts.append(candidate)
    return list(dict.fromkeys(contexts))


def _looks_explanatory(sentence: str, topic_key: str, nlp: Any) -> bool:
    lowered = str(sentence or "").lower()
    if not _looks_like_usable_text(sentence, require_sentence=True):
        return False
    if _ends_incomplete(sentence):
        return False
    if not _has_predicate(sentence, nlp):
        return False
    topic_terms = [token for token in re.split(r"[_\s]+", str(topic_key or "").lower()) if token]
    if any(term in lowered for term in topic_terms if len(term) > 3):
        return True
    return any(hint in lowered for hint in PEDAGOGICAL_HINTS)


def build_note_context_rows(snippet_rows: list[dict[str, Any]], *, spacy_model: str = "en_core_web_sm") -> tuple[list[dict[str, Any]], dict[str, Any]]:
    nlp = load_nlp(spacy_model)
    rows: list[dict[str, Any]] = []
    stats = {
        "source_rows": 0,
        "skipped_unmapped_topic": 0,
        "skipped_noisy_snippet": 0,
        "pairs_built": 0,
        "pairs_with_explicit_context": 0,
        "pairs_with_neighbor_context": 0,
        "pairs_missing_context": 0,
    }
    for snippet_row in snippet_rows:
        stats["source_rows"] += 1
        snippet_text = str(snippet_row.get("snippet_text") or "")
        topic_key = _norm(snippet_row.get("topic_key")).lower()
        book_template_id_sentence = topic_to_template_id("Sentence", topic_key)
        book_template_id_phrase = topic_to_template_id("Phrase", topic_key)
        if not (book_template_id_sentence or book_template_id_phrase):
            stats["skipped_unmapped_topic"] += 1
            continue
        if not _looks_like_usable_text(snippet_text, require_sentence=True):
            stats["skipped_noisy_snippet"] += 1
            continue
        sentences = _split_sentences(snippet_text, nlp)
        if not sentences:
            stats["skipped_noisy_snippet"] += 1
            continue

        explicit_contexts = _extract_explicit_contexts(snippet_text, nlp)
        explanation_candidates = [sent for sent in sentences if _looks_explanatory(sent, topic_key, nlp)]
        if not explanation_candidates:
            explanation_candidates = [
                sent
                for sent in sentences
                if _looks_like_usable_text(sent, require_sentence=True) and not _ends_incomplete(sent) and _has_predicate(sent, nlp)
            ][:1]

        context_candidates = [
            ctx for ctx in explicit_contexts if ctx not in explanation_candidates and _looks_like_context_material(ctx, nlp)
        ]
        pair_method = "explicit_context"
        if not context_candidates:
            context_candidates = [
                sent
                for sent in sentences
                if sent not in explanation_candidates and _looks_like_neighbor_context(sent, nlp)
            ]
            pair_method = "neighbor_sentence"
        if not explanation_candidates or not context_candidates:
            stats["pairs_missing_context"] += 1
            continue

        for explanation_text in explanation_candidates[:3]:
            for context_text in context_candidates[:2]:
                risk_flags: list[str] = []
                if pair_method == "explicit_context":
                    stats["pairs_with_explicit_context"] += 1
                else:
                    stats["pairs_with_neighbor_context"] += 1

                row = {
                    "row_id": _row_id(snippet_row, explanation_text, context_text),
                    "source_path": snippet_row.get("source_path"),
                    "parser_name": snippet_row.get("parser_name"),
                    "format": snippet_row.get("format"),
                    "topic_key": topic_key,
                    "anchor": snippet_row.get("anchor"),
                    "heading": snippet_row.get("heading"),
                    "snippet_text": snippet_text,
                    "explanation_text": explanation_text,
                    "context_text": context_text,
                    "pair_method": pair_method,
                    "risk_flags": risk_flags,
                    "book_template_id_sentence": book_template_id_sentence,
                    "book_template_id_phrase": book_template_id_phrase,
                }
                rows.append(row)
                stats["pairs_built"] += 1
    return rows, stats


def _walk_with_parent(
    node: dict[str, Any],
    *,
    parent: dict[str, Any] | None = None,
    path_types: list[str] | None = None,
    sibling_index: int = 0,
    sibling_count: int = 1,
):
    current_path = list(path_types or []) + [str(node.get("type") or "")]
    yield node, parent, current_path, sibling_index, sibling_count
    children = [child for child in (node.get("linguistic_elements") or []) if isinstance(child, dict)]
    for index, child in enumerate(children):
        yield from _walk_with_parent(
            child,
            parent=node,
            path_types=current_path,
            sibling_index=index,
            sibling_count=max(1, len(children)),
        )


def _template_ids_compatible(book_template_id: str, payload_template_id: str) -> bool:
    left = _norm(book_template_id)
    right = _norm(payload_template_id)
    if not left or not right:
        return False
    if left == right:
        return True
    compatibility = {
        "SENT_NEGATION_GENERAL": "SENT_NEGATION_",
        "SENT_CONDITIONAL_GENERAL": "SENT_CONDITIONAL_",
        "SENT_PASSIVE_GENERAL": "SENT_PASSIVE_",
        "PHRASE_PP_GENERAL": "PHRASE_PP_",
        "PHRASE_RELATIVE_CLAUSE": "PHRASE_RELATIVE_CLAUSE",
        "PHRASE_VP_GENERAL": "PHRASE_VP_",
    }
    prefix = compatibility.get(left)
    return bool(prefix and right.startswith(prefix))


def build_note_context_contract_rows(note_context_rows: list[dict[str, Any]], *, spacy_model: str = "en_core_web_sm") -> tuple[list[dict[str, Any]], dict[str, Any]]:
    nlp = load_nlp(spacy_model)
    out_rows: list[dict[str, Any]] = []
    stats = {
        "note_context_rows": len(note_context_rows),
        "contracts_built": 0,
        "contracts_failed": 0,
        "contracts_skipped_bad_context": 0,
        "matched_sentence_nodes": 0,
        "matched_phrase_nodes": 0,
    }
    for row in note_context_rows:
        context_text = _norm(row.get("context_text"))
        if not _looks_like_context_material(context_text, nlp):
            stats["contracts_skipped_bad_context"] += 1
            continue
        try:
            contract_doc = build_skeleton(context_text, nlp)
        except Exception:
            stats["contracts_failed"] += 1
            continue
        if not contract_doc:
            stats["contracts_failed"] += 1
            continue

        contract_doc = copy.deepcopy(contract_doc)
        for sentence_text, sentence_node in contract_doc.items():
            sentence_children = [child for child in (sentence_node.get("linguistic_elements") or []) if isinstance(child, dict)]
            sentence_payload = build_contract_template_payload(
                node=sentence_node,
                sentence_node=sentence_node,
                parent=None,
                path_types=["Sentence"],
                depth=0,
                sibling_index=0,
                sibling_count=1,
            )
            if sentence_payload is not None:
                sentence_node["contract_template_payload"] = sentence_payload
                book_sentence_template = _norm(row.get("book_template_id_sentence"))
                if _template_ids_compatible(book_sentence_template, sentence_payload.get("template_id") or ""):
                    sentence_node["book_templated_notes"] = [
                        {
                            "source": "book_explanation_context_v1",
                            "topic_key": row.get("topic_key"),
                            "explanation_text": row.get("explanation_text"),
                            "book_template_id": book_sentence_template,
                            "template_text": sentence_payload.get("template_text"),
                            "rendered_note_text": sentence_payload.get("rendered_note_text"),
                            "allowed_slots": sentence_payload.get("allowed_slots"),
                        }
                    ]
                    stats["matched_sentence_nodes"] += 1

            for index, child in enumerate(sentence_children):
                for node, parent, path_types, node_sibling_index, node_sibling_count in _walk_with_parent(
                    child,
                    parent=sentence_node,
                    path_types=["Sentence"],
                    sibling_index=index,
                    sibling_count=max(1, len(sentence_children)),
                ):
                    if str(node.get("type") or "") not in {"Phrase", "Sentence"}:
                        continue
                    payload = build_contract_template_payload(
                        node=node,
                        sentence_node=sentence_node,
                        parent=parent,
                        path_types=path_types,
                        depth=max(0, len(path_types) - 1),
                        sibling_index=node_sibling_index,
                        sibling_count=node_sibling_count,
                    )
                    if payload is None:
                        continue
                    node["contract_template_payload"] = payload
                    if str(node.get("type") or "") == "Phrase":
                        book_phrase_template = _norm(row.get("book_template_id_phrase"))
                        if _template_ids_compatible(book_phrase_template, payload.get("template_id") or ""):
                            node["book_templated_notes"] = [
                                {
                                    "source": "book_explanation_context_v1",
                                    "topic_key": row.get("topic_key"),
                                    "explanation_text": row.get("explanation_text"),
                                    "book_template_id": book_phrase_template,
                                    "template_text": payload.get("template_text"),
                                    "rendered_note_text": payload.get("rendered_note_text"),
                                    "allowed_slots": payload.get("allowed_slots"),
                                }
                            ]
                            stats["matched_phrase_nodes"] += 1

        out_rows.append(
            {
                "row_id": row.get("row_id"),
                "source_path": row.get("source_path"),
                "parser_name": row.get("parser_name"),
                "format": row.get("format"),
                "topic_key": row.get("topic_key"),
                "heading": row.get("heading"),
                "explanation_text": row.get("explanation_text"),
                "context_text": row.get("context_text"),
                "pair_method": row.get("pair_method"),
                "risk_flags": list(row.get("risk_flags") or []),
                "book_template_id_sentence": row.get("book_template_id_sentence"),
                "book_template_id_phrase": row.get("book_template_id_phrase"),
                "context_contract": contract_doc,
            }
        )
        stats["contracts_built"] += 1
    return out_rows, stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Build note-context corpus and context contracts from book snippets.")
    parser.add_argument("--input", required=True, help="Input snippets JSONL.")
    parser.add_argument("--output-note-context-jsonl", required=True)
    parser.add_argument("--output-contract-jsonl", required=True)
    parser.add_argument("--report-json", required=True)
    parser.add_argument("--spacy-model", default="en_core_web_sm")
    args = parser.parse_args()

    snippet_rows = list(_iter_jsonl(args.input))
    note_context_rows, note_context_report = build_note_context_rows(snippet_rows, spacy_model=args.spacy_model)
    contract_rows, contract_report = build_note_context_contract_rows(
        note_context_rows,
        spacy_model=args.spacy_model,
    )
    report = {
        "pipeline_version": "book_explanation_context_v1",
        "input": str(Path(args.input).resolve()),
        "spacy_model": args.spacy_model,
        "snippet_rows": len(snippet_rows),
        "note_context_report": note_context_report,
        "contract_report": contract_report,
    }
    _write_jsonl(args.output_note_context_jsonl, note_context_rows)
    _write_jsonl(args.output_contract_jsonl, contract_rows)
    _write_json(args.report_json, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
