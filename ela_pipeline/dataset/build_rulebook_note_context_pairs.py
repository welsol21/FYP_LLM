"""Build notation-context pairs from rulebook-style grammar dictionary rows."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from ela_pipeline.parse.spacy_parser import load_nlp


_CONTROL_GLYPH_RE = re.compile(r"[\x00-\x1f\uF000-\uF8FF]")
_WHITESPACE_RE = re.compile(r"\s+")
_PAGE_NUMBER_RE = re.compile(r"^\d{1,4}$")
_ROMAN_PAGE_RE = re.compile(r"^[ivxlcdm]+$", re.IGNORECASE)
_EXAMPLE_MARKER_RE = re.compile(r"\b(?:e\.g\.|for example|example:|examples:)\b", re.IGNORECASE)
_META_LINE_PREFIXES = (
    "see also ",
    "compare ",
    "also called ",
    "contrasted with ",
)
_META_TERMS = (
    "noun",
    "verb",
    "phrase",
    "clause",
    "word",
    "term",
    "grammar",
    "construction",
    "subject",
    "object",
    "complement",
    "predicator",
    "language",
    "entry",
    "entries",
    "meaning",
    "category",
    "class",
    "construction",
    "analysis",
)
_EXPLANATION_HINTS = (
    "used",
    "use ",
    "means",
    "refers",
    "indicate",
    "indicates",
    "designating",
    "designates",
    "expresses",
    "called",
    "contrasts",
    "signals",
    "functions",
    "omitted",
    "introduced",
    "denotes",
    "classiﬁcation",
    "classification",
)


def _norm(value: Any) -> str:
    value = _CONTROL_GLYPH_RE.sub(" ", str(value or ""))
    return _WHITESPACE_RE.sub(" ", value.strip())


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
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\f", "\n")
    return [_norm(line) for line in text.split("\n")]


def _line_slice(lines: list[str], start_line: int, end_line: int) -> list[str]:
    start = max(0, int(start_line) - 1)
    end = max(start, int(end_line))
    return [line for line in lines[start:end] if _norm(line)]


def _looks_meta_line(text: str) -> bool:
    lowered = _norm(text).lower()
    if not lowered:
        return True
    if _PAGE_NUMBER_RE.fullmatch(lowered) or _ROMAN_PAGE_RE.fullmatch(lowered):
        return True
    if any(lowered.startswith(prefix) for prefix in _META_LINE_PREFIXES):
        return True
    return False


def _looks_explanatory(text: str) -> bool:
    lowered = _norm(text).lower()
    if not lowered or _looks_meta_line(lowered):
        return False
    return any(hint in lowered for hint in _EXPLANATION_HINTS)


def _looks_short_example_line(text: str) -> bool:
    text = _norm(text)
    if not text or _looks_meta_line(text):
        return False
    words = re.findall(r"[A-Za-z']+", text)
    if not (2 <= len(words) <= 14):
        return False
    lowered = text.lower()
    if sum(term in lowered for term in _META_TERMS) >= 2:
        return False
    if any(token in lowered for token in ("e.g.", "for example", "example:", "examples:")):
        return False
    if text.endswith(":"):
        return False
    return bool(text[0].isupper() or "?" in text or "!" in text)


def _looks_example_candidate(text: str, nlp: Any) -> bool:
    text = _norm(text.strip(" ,;:"))
    if not text or _looks_meta_line(text):
        return False
    words = re.findall(r"[A-Za-z']+", text)
    if not (2 <= len(words) <= 20):
        return False
    lowered = text.lower()
    if sum(term in lowered for term in _META_TERMS) >= 2:
        return False
    if any(lowered.startswith(prefix) for prefix in ("for example", "example", "examples", "see ", "compare ")):
        return False
    if len(words) >= 8 and text[:1].islower():
        return False
    doc = nlp(text)
    has_verb = any(token.pos_ in {"VERB", "AUX"} for token in doc)
    if has_verb:
        return bool(text[:1].isupper() or "?" in text or "!" in text or len(words) <= 8)
    if "?" in text or "!" in text:
        return True
    return len(words) <= 6


def _strip_entry_head_prefix(text: str, entry_head: str) -> str:
    text = _norm(text)
    entry_head = _norm(entry_head)
    if not text or not entry_head:
        return text
    if text == entry_head:
        return ""
    lowered = text.lower()
    head_lower = entry_head.lower()
    if lowered.startswith(f"{head_lower} "):
        return _norm(text[len(entry_head) :])
    return text


def _looks_inline_headword(line: str) -> bool:
    line = _norm(line)
    if not line or line.endswith((".", "?", "!", ";", ":")):
        return False
    words = line.split()
    if not (1 <= len(words) <= 3):
        return False
    if any(ch.isdigit() for ch in line):
        return False
    if any(token in line.lower() for token in ("e.g.", "for example", "example:", "examples:")):
        return False
    return True


def _split_explicit_tail_into_examples(tail: str, nlp: Any) -> list[str]:
    tail = _norm(tail.strip(" :-"))
    if not tail:
        return []
    doc = nlp(tail)
    items = []
    for sent in doc.sents:
        candidate = _norm(sent.text)
        if _looks_example_candidate(candidate, nlp):
            items.append(candidate)
    if not items and _looks_example_candidate(tail, nlp):
        items.append(tail)
    return list(dict.fromkeys(items))


def _notation_from_buffer(buffer: list[str]) -> str:
    kept = [_norm(line) for line in buffer if _norm(line) and not _looks_meta_line(line)]
    return _norm(" ".join(kept[-3:]))


def _extract_pairs_from_row(row: dict[str, Any], payload_lines: list[str], nlp: Any) -> list[dict[str, Any]]:
    row_type = str(row.get("row_type") or "")
    if row_type not in {"dictionary_entry", "notational_rule"}:
        return []
    lines = _line_slice(payload_lines, int(row.get("line_start") or 0), int(row.get("line_end") or 0))
    if not lines:
        return []

    pairs: list[dict[str, Any]] = []
    notation_buffer: list[str] = []
    entry_head = _norm(row.get("entry_head") or row.get("heading"))
    idx = 0
    while idx < len(lines):
        line = _strip_entry_head_prefix(lines[idx], entry_head)
        if not line:
            idx += 1
            continue
        if _looks_inline_headword(line):
            notation_buffer = []
            idx += 1
            continue
        marker = _EXAMPLE_MARKER_RE.search(line)
        if marker:
            before = _norm(line[: marker.start()])
            after = _norm(line[marker.end() :])
            notation = _notation_from_buffer(notation_buffer + ([before] if before else []))
            examples = _split_explicit_tail_into_examples(after, nlp)
            j = idx + 1
            while j < len(lines):
                candidate = _strip_entry_head_prefix(lines[j], entry_head)
                if not _looks_example_candidate(candidate, nlp):
                    break
                examples.append(_norm(candidate))
                j += 1
            for context_text in list(dict.fromkeys([item for item in examples if item])):
                if notation and context_text:
                    pairs.append(
                        {
                            "source_path": row.get("source_path"),
                            "row_type": row_type,
                            "entry_head": row.get("entry_head") or row.get("heading"),
                            "heading": row.get("heading"),
                            "notation_text": notation,
                            "context_text": context_text,
                            "pair_method": "explicit_marker",
                        }
                    )
            if before:
                notation_buffer.append(before)
            idx = j
            continue

        if _looks_explanatory(line):
            notation_buffer.append(line)
            j = idx + 1
            block_examples: list[str] = []
            while j < len(lines):
                candidate = _strip_entry_head_prefix(lines[j], entry_head)
                if not _looks_example_candidate(candidate, nlp):
                    break
                block_examples.append(_norm(candidate))
                j += 1
            if block_examples:
                notation = _notation_from_buffer(notation_buffer)
                for context_text in block_examples:
                    if notation and context_text:
                        pairs.append(
                            {
                                "source_path": row.get("source_path"),
                                "row_type": row_type,
                                "entry_head": row.get("entry_head") or row.get("heading"),
                                "heading": row.get("heading"),
                                "notation_text": notation,
                                "context_text": context_text,
                                "pair_method": "line_block",
                            }
                        )
                idx = j
                continue
        elif not _looks_meta_line(line):
            notation_buffer.append(line)
        idx += 1
    return pairs


def build_rulebook_note_context_pairs(
    *,
    rulebook_jsonl: str,
    payload_txt: str,
    spacy_model: str = "en_core_web_sm",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    nlp = load_nlp(spacy_model)
    payload_lines = _normalize_payload_lines(payload_txt)
    rows = list(_iter_jsonl(rulebook_jsonl))

    pairs: list[dict[str, Any]] = []
    for row in rows:
        pairs.extend(_extract_pairs_from_row(row, payload_lines, nlp))

    report = {
        "pipeline_version": "rulebook_note_context_v1",
        "rulebook_jsonl": str(Path(rulebook_jsonl).resolve()),
        "payload_txt": str(Path(payload_txt).resolve()),
        "rows_seen": len(rows),
        "pairs_total": len(pairs),
        "explicit_marker_pairs": sum(1 for row in pairs if row.get("pair_method") == "explicit_marker"),
        "line_block_pairs": sum(1 for row in pairs if row.get("pair_method") == "line_block"),
        "distinct_entry_heads": len({str(row.get("entry_head") or "").strip().lower() for row in pairs if str(row.get("entry_head") or "").strip()}),
    }
    return pairs, report


def main() -> None:
    parser = argparse.ArgumentParser(description="Build notation-context pairs from rulebook rows.")
    parser.add_argument("--rulebook-jsonl", required=True)
    parser.add_argument("--payload-txt", required=True)
    parser.add_argument("--output-jsonl", required=True)
    parser.add_argument("--report-json", required=True)
    parser.add_argument("--spacy-model", default="en_core_web_sm")
    args = parser.parse_args()

    rows, report = build_rulebook_note_context_pairs(
        rulebook_jsonl=args.rulebook_jsonl,
        payload_txt=args.payload_txt,
        spacy_model=args.spacy_model,
    )
    _write_jsonl(args.output_jsonl, rows)
    _write_json(args.report_json, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
