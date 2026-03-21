"""Build a reference-derived synthetic corpus for Word-level notes.

Reference books are better suited to lexical/terminological micro-explanations
than to sentence/phrase note-context pairs. This builder:

1. extracts topic-focused snippets from reference-style books;
2. pulls explicit example contexts from those snippets;
3. builds contracts for the example contexts;
4. keeps only Word nodes that match the intended template family;
5. emits Word-level synthetic rows compatible with the current generator path.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from ela_pipeline.annotate.note_context import build_note_context_prompt
from ela_pipeline.dataset.book_extraction import UniversalBookExtractionEngine, build_default_parsers
from ela_pipeline.dataset.build_dataset import PROMPT_TEMPLATE_VERSION, _build_template_target
from ela_pipeline.parse.spacy_parser import load_nlp
from ela_pipeline.skeleton.builder import build_skeleton


WORD_REFERENCE_ANCHORS: dict[str, list[str]] = {
    "word_preposition": ["preposition", "prepositions"],
    "word_modal_auxiliary": ["modal auxiliary", "modal auxiliaries", "modal verb", "modal verbs"],
    "word_auxiliary_have": ["auxiliary have", "perfect have"],
    "word_possessive_pronoun": ["possessive pronoun", "possessive determiner"],
    "word_article_definite": ["definite article"],
    "word_participle": ["participle", "past participle", "present participle"],
    "word_ing_form": ["gerund", "-ing form", "ing form"],
    "word_common_noun": ["common noun", "common nouns"],
}

WORD_TOPIC_TO_TEMPLATE_IDS: dict[str, set[str]] = {
    "word_preposition": {"WORD_PREPOSITION"},
    "word_modal_auxiliary": {"WORD_AUX_MODAL"},
    "word_auxiliary_have": {"WORD_AUX_HAVE"},
    "word_possessive_pronoun": {"WORD_PRONOUN_POSSESSIVE"},
    "word_article_definite": {"WORD_ARTICLE_DEFINITE"},
    "word_participle": {"WORD_VERB_PARTICIPLE"},
    "word_ing_form": {"WORD_VERB_ING"},
    "word_common_noun": {"WORD_NOUN_COMMON"},
}

REFERENCE_MARKERS = ("dictionary", "glossary", "handbook", "reference", "grammar today")
EXAMPLE_MARKERS = ("for example", "for instance", "e.g.", "example:", "examples:")
QUOTED_RE = re.compile(r"[\"“'`](.{5,}?)['\"”`]")
TRAILING_NOTE_RE = re.compile(r"(\(cf\..*$|\[i\.e\..*$|\[cf\..*$|>\s.*$)", re.IGNORECASE)
CONTROL_GLYPH_RE = re.compile(r"[\x00-\x1f\uF000-\uF8FF]")
META_CONTEXT_PREFIXES = (
    "compare ",
    "see ",
    "see also ",
    "cf.",
    "cf ",
    "term ",
    "terms ",
    "definition ",
    "defined as ",
)
METALANGUAGE_MARKERS = (
    "predicator",
    "preposition",
    "prepositional phrase",
    "noun phrase",
    "verb phrase",
    "adverb phrase",
    "adjectival phrase",
    "clause",
    "clauses",
    "modal verb",
    "modal verbs",
    "grammar",
    "english",
    "class of words",
    "function of",
    "complement",
    "complements",
    "subject",
    "object",
    "used interchangeably",
)
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
    "a",
    "an",
    "the",
    "my",
    "your",
    "his",
    "her",
    "its",
    "our",
    "their",
    "some",
    "any",
    "this",
    "that",
    "these",
    "those",
}
BAD_WORD_TOKENS = {
    "see",
    "also",
    "cf",
    "compare",
    "example",
    "examples",
    "term",
    "terms",
    "grammar",
    "dictionary",
    "glossary",
    "handbook",
    "reference",
}
MODAL_FORMS = {"can", "could", "may", "might", "must", "shall", "should", "will", "would"}
HAVE_FORMS = {"have", "has", "had"}
POSSESSIVE_FORMS = {"my", "your", "his", "her", "its", "our", "their", "whose"}
WORD_POS_TO_UD = {
    "noun": "NOUN",
    "proper noun": "PROPN",
    "pronoun": "PRON",
    "verb": "VERB",
    "auxiliary verb": "AUX",
    "adjective": "ADJ",
    "adverb": "ADV",
    "preposition": "ADP",
    "article": "DET",
    "determiner": "DET",
    "coordinating conjunction": "CCONJ",
    "subordinating conjunction": "SCONJ",
    "particle": "PART",
    "numeral": "NUM",
    "interjection": "INTJ",
}


def _norm(value: Any) -> str:
    value = CONTROL_GLYPH_RE.sub(" ", str(value or ""))
    return " ".join(value.strip().split())


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


def _clean(text: str) -> str:
    text = _norm(text).replace("*", "")
    text = TRAILING_NOTE_RE.sub("", text).strip()
    text = re.sub(r"[\]\)]+[.?!]?$", "", text).strip()
    return _norm(text)


def _looks_like_usable_text(text: str, *, require_sentence: bool) -> bool:
    text = _norm(text)
    if not text:
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
    if first.pos_ in {"PRON", "PROPN", "DET"}:
        return True
    if first.pos_ == "NOUN" and first.text[:1].isupper():
        return True
    return False


def _ends_incomplete(text: str) -> bool:
    words = re.findall(r"[A-Za-z']+", text.lower())
    return bool(words and words[-1] in INCOMPLETE_ENDINGS)


def _looks_like_context_material(text: str, nlp: Any) -> bool:
    text = _clean(text)
    if not _looks_like_usable_text(text, require_sentence=False):
        return False
    lowered = text.lower()
    if lowered.startswith(META_CONTEXT_PREFIXES):
        return False
    if text.endswith((":",";")):
        return False
    if _ends_incomplete(text):
        return False
    if any(marker in lowered for marker in METALANGUAGE_MARKERS):
        return False
    if not _has_predicate(text, nlp):
        return False
    if not _has_subject(text, nlp):
        return False
    return _starts_like_example_clause(text, nlp)


def _is_reference_book(path: str) -> bool:
    lowered = str(path or "").lower()
    return any(marker in lowered for marker in REFERENCE_MARKERS)


def _extract_explicit_contexts(text: str, nlp: Any) -> list[str]:
    contexts: list[str] = []
    text = str(text or "")
    for match in QUOTED_RE.finditer(text):
        candidate = _clean(match.group(1))
        if _looks_like_context_material(candidate, nlp):
            contexts.append(candidate)
    lowered = text.lower()
    for marker in EXAMPLE_MARKERS:
        idx = lowered.find(marker)
        if idx < 0:
            continue
        tail = _clean(text[idx + len(marker) :].lstrip(" :-,"))
        for part in re.split(r"[;•]|(?<=[.?!])\s+|(?<=\))\s+", tail):
            candidate = _clean(part)
            if _looks_like_context_material(candidate, nlp):
                contexts.append(candidate)
    return list(dict.fromkeys(contexts))


def _walk_words(node: dict[str, Any], *, parent: dict[str, Any] | None = None, path_types: list[str] | None = None, depth: int = 0):
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


def _split_template_target(value: str) -> tuple[str, str]:
    template_id, _, note_text = str(value or "").partition("|")
    return template_id.strip(), note_text.strip()


def _word_template_features(node: dict[str, Any]) -> dict[str, list[str]]:
    pos_name = str(node.get("part_of_speech") or "").strip().lower()
    dep = str(node.get("dep_label") or "").strip() or "dep"
    raw_features = node.get("features") or {}
    morph = [
        f"{key}={value}"
        for key, value in sorted(raw_features.items())
        if value not in (None, "", "null")
    ]
    pos = WORD_POS_TO_UD.get(pos_name, "X")
    return {
        "pos": [pos],
        "tag": [pos],
        "dep": [dep],
        "morph": morph,
    }


def _primary_feature(features: dict[str, list[str]], key: str) -> str:
    values = [str(item).strip() for item in features.get(key, []) if str(item).strip()]
    return values[0] if values else ""


def _looks_participle(features: dict[str, list[str]]) -> bool:
    tags = {str(tag).upper() for tag in features.get("tag", [])}
    morph = " ".join(str(item) for item in features.get("morph", []))
    return "VBN" in tags or ("VerbForm=Part" in morph and "Tense=Past" in morph)


def _looks_gerund(features: dict[str, list[str]], word_text: str) -> bool:
    tags = {str(tag).upper() for tag in features.get("tag", [])}
    if "VBG" in tags:
        return True
    return str(word_text or "").lower().endswith("ing")


def _topic_template_match_is_strict(
    *,
    topic_key: str,
    template_id: str,
    word_text: str,
    features: dict[str, list[str]],
) -> bool:
    lowered = str(word_text or "").strip().lower()
    if not lowered or lowered in BAD_WORD_TOKENS or len(lowered) < 2:
        return False
    pos = _primary_feature(features, "pos").upper()
    dep = _primary_feature(features, "dep").lower()

    if topic_key == "word_preposition":
        return template_id == "WORD_PREPOSITION" and pos == "ADP"
    if topic_key == "word_modal_auxiliary":
        return template_id == "WORD_AUX_MODAL" and pos == "AUX" and lowered in MODAL_FORMS
    if topic_key == "word_auxiliary_have":
        return template_id == "WORD_AUX_HAVE" and pos == "AUX" and lowered in HAVE_FORMS
    if topic_key == "word_possessive_pronoun":
        return template_id == "WORD_PRONOUN_POSSESSIVE" and pos in {"PRON", "DET"} and (
            dep == "poss" or lowered in POSSESSIVE_FORMS
        )
    if topic_key == "word_article_definite":
        return template_id == "WORD_ARTICLE_DEFINITE" and pos == "DET" and lowered == "the"
    if topic_key == "word_participle":
        return template_id == "WORD_VERB_PARTICIPLE" and pos == "VERB" and _looks_participle(features)
    if topic_key == "word_ing_form":
        return template_id == "WORD_VERB_ING" and pos == "VERB" and _looks_gerund(features, lowered)
    if topic_key == "word_common_noun":
        return template_id == "WORD_NOUN_COMMON" and pos == "NOUN"
    return False


def build_reference_word_rows(
    *,
    input_path: str,
    cache_dir: str,
    spacy_model: str = "en_core_web_sm",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    engine = UniversalBookExtractionEngine(
        parsers=build_default_parsers(ocr_max_pages=5),
        topic_anchors=WORD_REFERENCE_ANCHORS,
        cache_dir=cache_dir,
    )
    nlp = load_nlp(spacy_model)

    snippet_rows: list[dict[str, Any]] = []
    for path in sorted(Path(input_path).glob("*")):
        if path.is_file() and _is_reference_book(str(path)):
            snippet_rows.extend(item.as_dict() for item in engine.extract_from_path(str(path)))

    out_rows: list[dict[str, Any]] = []
    stats: Counter[str] = Counter()
    for snippet in snippet_rows:
        topic_key = str(snippet.get("topic_key") or "").strip()
        allowed_templates = WORD_TOPIC_TO_TEMPLATE_IDS.get(topic_key, set())
        if not allowed_templates:
            stats["skipped_unmapped_topic"] += 1
            continue
        contexts = _extract_explicit_contexts(str(snippet.get("snippet_text") or ""), nlp)
        if not contexts:
            stats["snippets_without_explicit_example"] += 1
            continue
        for context_text in contexts[:3]:
            try:
                contract_doc = build_skeleton(context_text, nlp)
            except Exception:
                stats["contract_parse_error"] += 1
                continue
            if not contract_doc:
                stats["contract_parse_empty"] += 1
                continue
            for sentence_text, sentence_node in contract_doc.items():
                for node, parent, path_types, depth, sibling_index, sibling_count in _walk_words(sentence_node, path_types=[]):
                    word_text = _norm(node.get("content"))
                    features = _word_template_features(node)
                    tam_bucket = str(node.get("tam_construction") or "none").strip().lower() or "none"
                    target, reason = _build_template_target("Word", word_text, features, tam_bucket)
                    if not target:
                        if reason:
                            stats[f"template_filtered_{reason.lower()}"] += 1
                        continue
                    template_id, note_text = _split_template_target(target)
                    if template_id not in allowed_templates:
                        stats["word_template_mismatch"] += 1
                        continue
                    if not _topic_template_match_is_strict(
                        topic_key=topic_key,
                        template_id=template_id,
                        word_text=word_text,
                        features=features,
                    ):
                        stats["word_template_rejected_strict"] += 1
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
                            "target": note_text,
                            "level": "Word",
                            "tam_bucket": tam_bucket,
                            "prompt_template_version": PROMPT_TEMPLATE_VERSION,
                            "task": "linguistic_note",
                            "template_id": template_id,
                            "topic_key": topic_key,
                            "word_text": word_text,
                            "sentence_text": sentence_text,
                            "source_path": snippet.get("source_path"),
                            "heading": snippet.get("heading"),
                            "snippet_text": snippet.get("snippet_text"),
                        }
                    )
                    stats["rows_emitted"] += 1
    report = {
        "pipeline_version": "reference_word_synthetic_v1",
        "input_path": str(Path(input_path).resolve()),
        "cache_dir": str(Path(cache_dir).resolve()),
        "spacy_model": spacy_model,
        "snippet_rows": len(snippet_rows),
        "rows_emitted": len(out_rows),
        "stats": dict(stats),
    }
    return out_rows, report


def main() -> None:
    parser = argparse.ArgumentParser(description="Build reference-derived synthetic Word corpus.")
    parser.add_argument("--input", required=True, help="Directory with selected reference books.")
    parser.add_argument("--output-jsonl", required=True)
    parser.add_argument("--report-json", required=True)
    parser.add_argument("--cache-dir", default="data/processed_book_text_cache")
    parser.add_argument("--spacy-model", default="en_core_web_sm")
    args = parser.parse_args()

    rows, report = build_reference_word_rows(
        input_path=args.input,
        cache_dir=args.cache_dir,
        spacy_model=args.spacy_model,
    )
    _write_jsonl(args.output_jsonl, rows)
    _write_json(args.report_json, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
