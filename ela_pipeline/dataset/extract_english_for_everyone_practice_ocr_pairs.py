"""Extract source-first note/context pairs from English for Everyone Practice Book via OCR."""

from __future__ import annotations

import argparse
from difflib import SequenceMatcher
import json
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from ela_pipeline.parse.spacy_parser import load_nlp


_CONTROL_RE = re.compile(r"[\x00-\x1f\uF000-\uF8FF]")
_WS_RE = re.compile(r"\s+")
_PAGE_ONLY_RE = re.compile(r"^\d{1,4}$")
_EXERCISE_MARKER_RE = re.compile(
    r"\b(?:FILL IN|COMPLETE THE SENTENCES|MARK THE SENTENCES|MATCH THE|REWRITE THE|CROSS OUT|"
    r"LOOK AT THE PICTURES|ADD QUESTION TAGS|WRITE EACH SENTENCE|WRITE THE|MARK WHETHER)\b",
    re.IGNORECASE,
)
_HEADING_SKIP_RE = re.compile(r"^(?:how to use this book|contents|answers)$", re.IGNORECASE)
_HEADING_CLEAN_RE = re.compile(r"^[^A-Za-z]+|[^A-Za-z]+$")
_HEADING_BODY_RE = re.compile(r"^[A-Za-z0-9'\",/& -]+$")
_PAREN_ANSWER_RE = re.compile(r"\(([A-Za-z][A-Za-z'/-]{0,20})\)")
_UNDERSCORE_RE = re.compile(r"_+")
_TRAILING_MARK_RE = re.compile(r"(?:\s+[\[\]_|(){}Oo0Il/\\-]+)+$")
_LEADING_GARBAGE_RE = re.compile(r"^[^A-Za-z0-9\"']+")
_SENTENCE_FRAGMENT_RE = re.compile(r"[^.?!]*[.?!]")
_EXPLANATION_HINT_RE = re.compile(
    r"\b(?:is used|are used|is a|are a|are an|can be used|can use|is formed|are formed|describes|describe|"
    r"refers to|used to|allows|identify|invites|express|expresses|talk about|show|shows)\b",
    re.IGNORECASE,
)
_FILLED_UNDERSCORE_RE = re.compile(r"_{1,}\s*[A-Za-z][A-Za-z'/-]{0,20}\s*_{1,}|[A-Za-z][A-Za-z'/-]{0,20}_{2,}|_{2,}[A-Za-z][A-Za-z'/-]{0,20}")
_SUSPICIOUS_OCR_TOKEN_RE = re.compile(
    r"\b(?:workes|finishs|brushs|watchs|washs|teachs|playes|gos|acomputer|youa|nota|amn't)\b",
    re.IGNORECASE,
)

_TOPIC_HINTS = {
    "passive_voice": ("passive",),
    "conditional_sentences": ("conditional",),
    "question_tags": ("question tags",),
    "relative_clauses": ("relative",),
    "prepositions": ("preposition",),
    "modal": ("modal", "ability", "permission", "obligations", "possibility", "suggestions"),
}
_COMMON_STARTERS = {
    "a",
    "an",
    "are",
    "am",
    "is",
    "was",
    "were",
    "can",
    "could",
    "did",
    "do",
    "does",
    "have",
    "has",
    "had",
    "he",
    "how",
    "i",
    "if",
    "it",
    "my",
    "she",
    "there",
    "they",
    "this",
    "we",
    "what",
    "when",
    "where",
    "who",
    "why",
    "you",
}


@dataclass(slots=True)
class PracticeOcrSection:
    source_path: str
    row_type: str
    topic_key: str
    heading: str
    rule_text: str
    page_start: int
    page_end: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PracticeSectionIndex:
    heading: str
    topic_key: str
    page_start: int
    page_end: int


def _norm(value: Any) -> str:
    value = _CONTROL_RE.sub(" ", str(value or ""))
    return _WS_RE.sub(" ", value.strip())


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


def _cache_dir_for_pdf(source_path: str) -> Path:
    source = Path(source_path)
    cache_root = Path("data/processed_book_text_cache")
    candidates = list(cache_root.glob(f"{source.stem.replace(' ', '_')}*"))
    if candidates:
        return candidates[0]
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", source.stem).strip("._") or "book"
    return cache_root / safe


def _cached_payload_text(source_path: str) -> str:
    payload_txt = _cache_dir_for_pdf(source_path) / "payload.txt"
    if not payload_txt.exists():
        return ""
    return payload_txt.read_text(encoding="utf-8", errors="ignore")


def _ocr_page_text(source_path: str, page_num: int, cache_dir: Path, *, ocr_psm: int = 11) -> str:
    ocr_dir = cache_dir / f"ocr_pages_psm{int(ocr_psm)}"
    ocr_dir.mkdir(parents=True, exist_ok=True)
    out_txt = ocr_dir / f"page_{page_num:04d}.txt"
    if out_txt.exists():
        return out_txt.read_text(encoding="utf-8", errors="ignore")

    with TemporaryDirectory(prefix="efe11_ocr_") as tmpdir:
        image_prefix = Path(tmpdir) / "page"
        subprocess.run(
            [
                "pdftoppm",
                "-f",
                str(page_num),
                "-l",
                str(page_num),
                "-png",
                source_path,
                str(image_prefix),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        image_files = sorted(Path(tmpdir).glob("page-*.png"))
        if not image_files:
            out_txt.write_text("", encoding="utf-8")
            return ""
        result = subprocess.run(
            ["tesseract", str(image_files[0]), "stdout", "--psm", str(int(ocr_psm))],
            check=True,
            capture_output=True,
            text=True,
        )
        text = result.stdout
    out_txt.write_text(text, encoding="utf-8")
    return text


def _normalize_lines(text: str) -> list[str]:
    raw = str(text or "").replace("\r\n", "\n").replace("\r", "\n").replace("\f", "\n")
    return [_norm(line) for line in raw.split("\n")]


def _extract_sections_from_contents(source_path: str, *, page_start: int, page_end: int) -> list[PracticeSectionIndex]:
    text = _cached_payload_text(source_path)
    if not text:
        return []
    lines = _normalize_lines(text)
    in_contents = False
    raw_sections: list[tuple[str, int]] = []
    idx = 0
    while idx < len(lines):
        line = lines[idx]
        lowered = line.lower()
        if lowered == "contents":
            in_contents = True
            idx += 1
            continue
        if not in_contents:
            idx += 1
            continue
        if line == "Answers":
            break

        match = re.match(r"^(?P<head>.+?)\s+(?P<page>\d{1,3})$", line)
        if match:
            heading = _norm(match.group("head"))
            page = int(match.group("page"))
            if page_start <= page <= page_end:
                raw_sections.append((heading, page))
            idx += 1
            continue

        next_idx = idx + 1
        while next_idx < len(lines) and not lines[next_idx]:
            next_idx += 1
        if line and next_idx < len(lines) and _PAGE_ONLY_RE.fullmatch(lines[next_idx]):
            page = int(lines[next_idx])
            if page_start <= page <= page_end:
                raw_sections.append((_norm(line), page))
            idx = next_idx + 1
            continue
        idx += 1

    deduped: list[tuple[str, int]] = []
    seen_pages: set[int] = set()
    for heading, page in raw_sections:
        if page in seen_pages:
            continue
        seen_pages.add(page)
        deduped.append((heading, page))
    deduped.sort(key=lambda item: item[1])
    out: list[PracticeSectionIndex] = []
    for idx, (heading, start) in enumerate(deduped):
        end = page_end if idx == len(deduped) - 1 else min(page_end, deduped[idx + 1][1] - 1)
        if start > end:
            continue
        out.append(
            PracticeSectionIndex(
                heading=heading,
                topic_key=_infer_topic_key(heading),
                page_start=start,
                page_end=end,
            )
        )
    return out


def _looks_heading(line: str) -> bool:
    clean = _HEADING_CLEAN_RE.sub("", _norm(line))
    if not clean or _PAGE_ONLY_RE.fullmatch(clean):
        return False
    if _HEADING_SKIP_RE.match(clean):
        return False
    if not _HEADING_BODY_RE.fullmatch(clean):
        return False
    if _EXERCISE_MARKER_RE.search(clean):
        return False
    if clean.endswith((".", "?", "!", ":")) or "." in clean:
        return False
    words = clean.split()
    if not (2 <= len(words) <= 8):
        return False
    alpha_words = [word for word in words if re.search(r"[A-Za-z]", word)]
    if len(alpha_words) < 2:
        return False
    capitals = sum(1 for word in alpha_words if word[:1].isupper())
    return capitals >= max(1, len(alpha_words) // 2)


def _infer_topic_key(heading: str) -> str:
    lowered = _norm(heading).lower()
    for topic_key, hints in _TOPIC_HINTS.items():
        if any(hint in lowered for hint in hints):
            return topic_key
    return ""


def _extract_heading_and_rule(lines: list[str], expected_heading: str = "") -> tuple[str, str] | None:
    heading_idx = -1
    heading = ""
    expected_key = _similarity_key(expected_heading)
    for idx, line in enumerate(lines[:8]):
        clean = _HEADING_CLEAN_RE.sub("", _norm(line)).strip()
        if not clean:
            continue
        if expected_key and expected_key and _similarity_key(clean) == expected_key:
            heading_idx = idx
            heading = expected_heading
            break
        if _looks_heading(line):
            heading_idx = idx
            heading = clean
            break
    if heading_idx < 0 or not heading:
        return None

    rule_lines: list[str] = []
    for line in lines[heading_idx + 1 :]:
        if not line or _PAGE_ONLY_RE.fullmatch(line):
            continue
        if _EXERCISE_MARKER_RE.search(line):
            break
        if _looks_heading(line):
            break
        rule_lines.append(line)
    rule_text = _norm(" ".join(rule_lines))
    if len(re.findall(r"[A-Za-z]{2,}", rule_text)) < 8:
        return None
    if not _EXPLANATION_HINT_RE.search(rule_text):
        return None
    return heading, rule_text


def _clean_sentence_candidate(text: str) -> str:
    text = _norm(text)
    text = _LEADING_GARBAGE_RE.sub("", text)
    text = _UNDERSCORE_RE.sub(" ", text)
    text = _PAREN_ANSWER_RE.sub("", text)
    text = _TRAILING_MARK_RE.sub("", text)
    text = _norm(text)
    while True:
        words = text.split()
        if not words:
            break
        first = re.sub(r"[^A-Za-z']", "", words[0])
        if not first:
            words = words[1:]
            text = " ".join(words)
            continue
        if first.lower() in _COMMON_STARTERS or (len(first) > 2 and first[:1].isupper()):
            break
        if len(words) == 1:
            break
        text = " ".join(words[1:])
        text = _norm(text)
    return text.strip(" -")


def _inflected_forms(base: str) -> set[str]:
    base = re.sub(r"[^A-Za-z]", "", base).lower()
    if not base:
        return set()
    forms = {base}
    forms.add(base + "s")
    forms.add(base + "ed")
    forms.add(base + "ing")
    if base.endswith("e"):
        forms.add(base[:-1] + "ing")
        forms.add(base + "d")
    if base.endswith(("s", "sh", "ch", "x", "z", "o")):
        forms.add(base + "es")
    if len(base) > 1 and base.endswith("y") and base[-2] not in "aeiou":
        forms.add(base[:-1] + "ies")
        forms.add(base[:-1] + "ied")
    return forms


def _has_prefilled_parenthetical_answer(raw_line: str) -> bool:
    match = re.search(r"\b([A-Za-z][A-Za-z'-]+)\s+\(([A-Za-z][A-Za-z'/-]{0,20})\)", raw_line)
    if not match:
        return False
    answered = re.sub(r"[^A-Za-z]", "", match.group(1)).lower()
    base = re.sub(r"[^A-Za-z]", "", match.group(2)).lower()
    if not answered or not base:
        return False
    return answered in _inflected_forms(base) and answered != base


def _has_filled_underscore_answer(raw_line: str) -> bool:
    return bool(_FILLED_UNDERSCORE_RE.search(raw_line))


def _sentence_score(text: str, nlp: Any) -> float:
    doc = nlp(text)
    score = 0.0
    for token in doc:
        if not token.is_alpha:
            continue
        prob = float(token.lex.prob)
        if prob <= -20:
            score -= 8.0
        else:
            score += prob
    return score


def _looks_sentence(text: str, nlp: Any) -> bool:
    if len(re.findall(r"[A-Za-z']+", text)) < 3:
        return False
    doc = nlp(text)
    has_pred = any(token.pos_ in {"VERB", "AUX"} for token in doc)
    has_subject = any(token.dep_ in {"nsubj", "nsubjpass", "expl", "csubj"} for token in doc)
    if not has_pred:
        return False
    if not text.endswith("?"):
        return bool(has_subject)
    tokens = [token for token in doc if not token.is_space]
    if not tokens:
        return False
    first = tokens[0].lower_
    question_like = first in {
        "am",
        "are",
        "is",
        "was",
        "were",
        "do",
        "does",
        "did",
        "have",
        "has",
        "had",
        "can",
        "could",
        "will",
        "would",
        "shall",
        "should",
        "may",
        "might",
        "must",
        "who",
        "what",
        "when",
        "where",
        "why",
        "how",
    }
    if not question_like or len(tokens) < 2:
        return False
    second = tokens[1]
    second_is_subject_like = second.pos_ in {"PRON", "PROPN", "NOUN"} or second.lower_ in {
        "i",
        "you",
        "he",
        "she",
        "it",
        "we",
        "they",
        "who",
    }
    return bool(second_is_subject_like)


def _looks_clean_for_high_confidence(text: str) -> bool:
    cleaned = _norm(text)
    if not cleaned:
        return False
    if _SUSPICIOUS_OCR_TOKEN_RE.search(cleaned):
        return False
    return True


def _similarity_key(text: str) -> str:
    return re.sub(r"[^a-z]+", " ", text.lower()).strip()


def _near_duplicate(left: str, right: str) -> bool:
    left_key = _similarity_key(left)
    right_key = _similarity_key(right)
    if not left_key or not right_key:
        return False
    return SequenceMatcher(None, left_key, right_key).ratio() >= 0.9


def _extract_examples_from_page(page_text: str, *, nlp: Any) -> list[dict[str, Any]]:
    lines = _normalize_lines(page_text)
    first_exercise_idx = next((idx for idx, line in enumerate(lines) if _EXERCISE_MARKER_RE.search(line)), None)
    if first_exercise_idx is not None:
        lines = lines[first_exercise_idx + 1 :]
    examples: list[dict[str, Any]] = []

    for line in lines:
        raw_line = _norm(line)
        if not raw_line or _PAGE_ONLY_RE.fullmatch(raw_line) or _EXERCISE_MARKER_RE.search(raw_line):
            continue

        if "(" in raw_line or "_" in raw_line:
            has_prefilled = _has_prefilled_parenthetical_answer(raw_line)
            has_filled_underscore = _has_filled_underscore_answer(raw_line)
            if not has_prefilled and not has_filled_underscore:
                continue
            cleaned = _clean_sentence_candidate(raw_line)
            for fragment in _SENTENCE_FRAGMENT_RE.findall(cleaned):
                fragment = _clean_sentence_candidate(fragment)
                if fragment and _looks_sentence(fragment, nlp):
                    confidence = "high" if _looks_clean_for_high_confidence(fragment) else "medium"
                    examples.append(
                        {
                            "context_text": fragment,
                            "example_label": "answered_example",
                            "confidence": confidence,
                            "raw_ocr_line": raw_line,
                        }
                    )
            continue

        for fragment in _SENTENCE_FRAGMENT_RE.findall(raw_line):
            cleaned = _clean_sentence_candidate(fragment)
            if not cleaned or not _looks_sentence(cleaned, nlp):
                continue
            examples.append(
                {
                    "context_text": cleaned,
                    "example_label": "choice_candidate",
                    "confidence": "medium",
                    "raw_ocr_line": raw_line,
                }
            )

    merged: list[dict[str, Any]] = []
    for item in examples:
        text = str(item.get("context_text") or "")
        if not text:
            continue
        score = _sentence_score(str(item["context_text"]), nlp)
        item["language_score"] = score
        replaced = False
        for idx, existing in enumerate(merged):
            if _near_duplicate(text, str(existing.get("context_text") or "")):
                if float(item["language_score"]) > float(existing.get("language_score", -999.0)):
                    merged[idx] = item
                replaced = True
                break
        if not replaced:
            merged.append(item)
    out = list(merged)
    out.sort(key=lambda row: (0 if row.get("confidence") == "high" else 1, -float(row.get("language_score", -999.0))))
    return out


def extract_english_for_everyone_practice_ocr_pairs(
    *,
    source_path: str,
    page_start: int = 8,
    page_end: int = 324,
    spacy_model: str = "en_core_web_sm",
    ocr_psm: int = 11,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    nlp = load_nlp(spacy_model)
    cache_dir = _cache_dir_for_pdf(source_path)

    rows: list[PracticeOcrSection] = []
    pairs: list[dict[str, Any]] = []
    section_index = _extract_sections_from_contents(source_path, page_start=page_start, page_end=page_end)

    stats = {
        "pages_scanned": 0,
        "sections_found": 0,
        "pairs_total": 0,
        "high_confidence_pairs": 0,
        "medium_confidence_pairs": 0,
    }

    if not section_index:
        for page_num in range(int(page_start), int(page_end) + 1):
            stats["pages_scanned"] += 1
            page_text = _ocr_page_text(source_path, page_num, cache_dir, ocr_psm=ocr_psm)
            lines = _normalize_lines(page_text)
            heading_and_rule = _extract_heading_and_rule(lines)
            if heading_and_rule is None:
                continue
            heading, rule_text = heading_and_rule
            topic_key = _infer_topic_key(heading)
            rows.append(
                PracticeOcrSection(
                    source_path=source_path,
                    row_type="practice_book_ocr_section",
                    topic_key=topic_key,
                    heading=heading,
                    rule_text=rule_text,
                    page_start=page_num,
                    page_end=page_num,
                )
            )
            stats["sections_found"] += 1
            for example in _extract_examples_from_page(page_text, nlp=nlp):
                pair = {
                    "source_path": source_path,
                    "row_type": "practice_book_ocr_pair",
                    "heading": heading,
                    "topic_key": topic_key,
                    "notation_text": rule_text,
                    "context_text": example["context_text"],
                    "pair_method": "ocr_page_example",
                    "example_label": example["example_label"],
                    "confidence": example["confidence"],
                    "page_num": page_num,
                    "raw_ocr_line": example["raw_ocr_line"],
                }
                pairs.append(pair)
                stats["pairs_total"] += 1
                if example["confidence"] == "high":
                    stats["high_confidence_pairs"] += 1
                else:
                    stats["medium_confidence_pairs"] += 1
    else:
        for section in section_index:
            stats["sections_found"] += 1
            rule_text = ""
            for page_num in range(section.page_start, section.page_end + 1):
                stats["pages_scanned"] += 1
                page_text = _ocr_page_text(source_path, page_num, cache_dir, ocr_psm=ocr_psm)
                if not rule_text:
                    parsed = _extract_heading_and_rule(_normalize_lines(page_text), expected_heading=section.heading)
                    if parsed is not None:
                        _heading, rule_text = parsed
                    else:
                        top_lines = _normalize_lines(page_text)
                        fallback_rule: list[str] = []
                        for line in top_lines[:12]:
                            if not line or _PAGE_ONLY_RE.fullmatch(line):
                                continue
                            if _EXERCISE_MARKER_RE.search(line):
                                break
                            fallback_rule.append(line)
                        candidate_rule = _norm(" ".join(fallback_rule))
                        if _EXPLANATION_HINT_RE.search(candidate_rule):
                            rule_text = candidate_rule
                for example in _extract_examples_from_page(page_text, nlp=nlp):
                    pair = {
                        "source_path": source_path,
                        "row_type": "practice_book_ocr_pair",
                        "heading": section.heading,
                        "topic_key": section.topic_key,
                        "notation_text": rule_text,
                        "context_text": example["context_text"],
                        "pair_method": "ocr_page_example",
                        "example_label": example["example_label"],
                        "confidence": example["confidence"],
                        "page_num": page_num,
                        "raw_ocr_line": example["raw_ocr_line"],
                    }
                    pairs.append(pair)
                    stats["pairs_total"] += 1
                    if example["confidence"] == "high":
                        stats["high_confidence_pairs"] += 1
                    else:
                        stats["medium_confidence_pairs"] += 1
            rows.append(
                PracticeOcrSection(
                    source_path=source_path,
                    row_type="practice_book_ocr_section",
                    topic_key=section.topic_key,
                    heading=section.heading,
                    rule_text=rule_text,
                    page_start=section.page_start,
                    page_end=section.page_end,
                )
            )
    report = {
        "pipeline_version": "english_for_everyone_practice_ocr_pairs_v2",
        "source_path": source_path,
        "page_start": int(page_start),
        "page_end": int(page_end),
        "spacy_model": spacy_model,
        "ocr_psm": int(ocr_psm),
        "stats": stats,
        "topic_counts": {
            key: sum(1 for row in pairs if row.get("topic_key") == key)
            for key in sorted({str(row.get("topic_key") or "") for row in pairs})
        },
    }
    return [row.as_dict() for row in rows], pairs, report


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract OCR note/context pairs from English for Everyone Practice Book.")
    parser.add_argument("--input-pdf", required=True)
    parser.add_argument("--output-rows-jsonl", required=True)
    parser.add_argument("--output-pairs-jsonl", required=True)
    parser.add_argument("--report-json", required=True)
    parser.add_argument("--page-start", type=int, default=8)
    parser.add_argument("--page-end", type=int, default=324)
    parser.add_argument("--spacy-model", default="en_core_web_sm")
    parser.add_argument("--ocr-psm", type=int, default=11)
    args = parser.parse_args()

    rows, pairs, report = extract_english_for_everyone_practice_ocr_pairs(
        source_path=args.input_pdf,
        page_start=args.page_start,
        page_end=args.page_end,
        spacy_model=args.spacy_model,
        ocr_psm=args.ocr_psm,
    )
    _write_jsonl(args.output_rows_jsonl, rows)
    _write_jsonl(args.output_pairs_jsonl, pairs)
    _write_json(args.report_json, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
