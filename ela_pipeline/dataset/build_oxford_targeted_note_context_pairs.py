"""Build high-precision note-context pairs from targeted Oxford Dictionary entries."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ela_pipeline.dataset.build_rulebook_note_context_pairs import (
    _looks_example_candidate,
    _looks_explanatory,
    _norm,
    _normalize_payload_lines,
    _notation_from_buffer,
    _split_explicit_tail_into_examples,
)
from ela_pipeline.parse.spacy_parser import load_nlp


@dataclass(frozen=True)
class OxfordTopicBlock:
    entry_head: str
    topic_key: str
    start_marker: str
    end_markers: tuple[str, ...]


TARGET_BLOCKS = (
    OxfordTopicBlock(
        entry_head="conditional",
        topic_key="conditional_sentences",
        start_marker="conditional (adj.)",
        end_markers=("conditioning The phenomenon",),
    ),
    OxfordTopicBlock(
        entry_head="passive",
        topic_key="passive_voice",
        start_marker="passive (adj.)",
        end_markers=("passive auxiliary be See passive.", "past (n. & adj.)"),
    ),
    OxfordTopicBlock(
        entry_head="preposition",
        topic_key="prepositions",
        start_marker="preposition A word that belongs",
        end_markers=("prepositional Of, pertaining to,",),
    ),
    OxfordTopicBlock(
        entry_head="prepositional phrase",
        topic_key="prepositional_phrases",
        start_marker="prepositional phrase (PP)",
        end_markers=("prepositional verb A *verb",),
    ),
    OxfordTopicBlock(
        entry_head="question tag",
        topic_key="question_tags",
        start_marker="tag (n.)",
        end_markers=("tautology The saying",),
    ),
    OxfordTopicBlock(
        entry_head="relative clause",
        topic_key="relative_clauses",
        start_marker="relative (n. & adj.)",
        end_markers=("relativity See sapir–whorf hypothesis, the.",),
    ),
    OxfordTopicBlock(
        entry_head="that-clause",
        topic_key="that_clause",
        start_marker="that-clause A clause beginning",
        end_markers=("thematic Of, pertaining to,",),
    ),
)

_COMMON_PREPOSITIONS = {
    "about",
    "above",
    "across",
    "after",
    "against",
    "along",
    "around",
    "at",
    "before",
    "behind",
    "below",
    "beside",
    "between",
    "by",
    "for",
    "from",
    "in",
    "inside",
    "into",
    "near",
    "of",
    "off",
    "on",
    "out",
    "over",
    "through",
    "to",
    "under",
    "with",
}


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


def _find_line(lines: list[str], marker: str) -> int:
    marker = _norm(marker)
    for idx, line in enumerate(lines):
        if _norm(line) == marker:
            return idx
    return -1


def _find_line_contains(lines: list[str], marker: str, *, start_idx: int = 0) -> int:
    marker = _norm(marker).lower()
    for idx in range(max(0, start_idx), len(lines)):
        if marker in _norm(lines[idx]).lower():
            return idx
    return -1


def _block_slice(lines: list[str], spec: OxfordTopicBlock) -> tuple[int, int] | None:
    start_idx = _find_line_contains(lines, spec.start_marker)
    if start_idx < 0:
        return None
    end_idx = len(lines)
    for marker in spec.end_markers:
        marker_idx = _find_line_contains(lines, marker, start_idx=start_idx + 1)
        if marker_idx >= 0:
            end_idx = min(end_idx, marker_idx)
    if end_idx <= start_idx:
        return None
    return start_idx, end_idx


def _extract_pairs_from_block(
    *,
    lines: list[str],
    spec: OxfordTopicBlock,
    source_path: str,
    nlp: Any,
) -> list[dict[str, Any]]:
    notation_buffer: list[str] = []
    pairs: list[dict[str, Any]] = []
    idx = 0
    while idx < len(lines):
        line = _norm(lines[idx])
        if not line:
            idx += 1
            continue
        if line.lower().startswith(spec.entry_head.lower() + " "):
            line = _norm(line[len(spec.entry_head) :])
            if not line:
                idx += 1
                continue
        if "e.g." in line.lower() or "for example" in line.lower():
            marker_text = "e.g." if "e.g." in line.lower() else "for example"
            split_at = line.lower().find(marker_text)
            before = _norm(line[:split_at])
            after = _norm(line[split_at + len(marker_text) :])
            notation = _notation_from_buffer(notation_buffer + ([before] if before else []))
            examples = _split_explicit_tail_into_examples(after, nlp)
            j = idx + 1
            while j < len(lines) and _looks_example_candidate(lines[j], nlp):
                examples.append(_norm(lines[j]))
                j += 1
            for context_text in list(dict.fromkeys([item for item in examples if item])):
                if notation and context_text and _topic_allows_context(spec, context_text, nlp):
                    pairs.append(
                        {
                            "source_path": source_path,
                            "entry_head": spec.entry_head,
                            "topic_key": spec.topic_key,
                            "notation_text": notation,
                            "context_text": context_text,
                            "pair_method": "oxford_targeted",
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
            while j < len(lines) and _looks_example_candidate(lines[j], nlp):
                block_examples.append(_norm(lines[j]))
                j += 1
            if block_examples:
                notation = _notation_from_buffer(notation_buffer)
                for context_text in block_examples:
                    if notation and context_text and _topic_allows_context(spec, context_text, nlp):
                        pairs.append(
                            {
                                "source_path": source_path,
                                "entry_head": spec.entry_head,
                                "topic_key": spec.topic_key,
                                "notation_text": notation,
                                "context_text": context_text,
                                "pair_method": "oxford_targeted",
                            }
                        )
                idx = j
                continue
        elif _looks_example_candidate(line, nlp):
            notation = _notation_from_buffer(notation_buffer)
            if notation and _topic_allows_context(spec, line, nlp):
                pairs.append(
                    {
                        "source_path": source_path,
                        "entry_head": spec.entry_head,
                        "topic_key": spec.topic_key,
                        "notation_text": notation,
                        "context_text": line,
                        "pair_method": "oxford_targeted",
                    }
                )
        else:
            notation_buffer.append(line)
        idx += 1
    deduped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in pairs:
        key = (
            str(row.get("entry_head") or ""),
            str(row.get("notation_text") or ""),
            str(row.get("context_text") or ""),
        )
        deduped[key] = row
    return list(deduped.values())


def _topic_allows_context(spec: OxfordTopicBlock, text: str, nlp: Any) -> bool:
    text = _norm(text)
    if not text:
        return False
    lowered = text.lower()
    words = re.findall(r"[A-Za-z']+", text)
    has_verb = any(token.pos_ in {"VERB", "AUX"} for token in nlp(text))
    if spec.topic_key == "conditional_sentences":
        return any(marker in lowered for marker in ("if ", "unless ", "provided ", "providing ")) and has_verb
    if spec.topic_key == "that_clause":
        if "*" in text:
            return False
        return has_verb and (
            lowered.startswith("that ")
            or "(that)" in lowered
            or " ø " in f" {lowered} "
        )
    if spec.topic_key == "prepositions":
        first = words[0].lower() if words else ""
        return bool(
            "?" in text
            or "!" in text
            or (len(words) <= 8 and first in _COMMON_PREPOSITIONS)
        )
    if spec.topic_key == "prepositional_phrases":
        first = words[0].lower() if words else ""
        return len(words) <= 8 and bool(first in _COMMON_PREPOSITIONS or text[:1].islower())
    if spec.topic_key == "question_tags":
        return bool("?" in text or re.search(r",\s*[A-Za-z].+\?$", text))
    if spec.topic_key == "relative_clauses":
        first = words[0].lower() if words else ""
        return bool(first in {"who", "which", "that", "whom", "whose", "where", "when"} or lowered.startswith("the "))
    return True


def build_oxford_targeted_note_context_pairs(
    *,
    payload_txt: str,
    source_path: str = "",
    spacy_model: str = "en_core_web_sm",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    lines = _normalize_payload_lines(payload_txt)
    nlp = load_nlp(spacy_model)
    pairs: list[dict[str, Any]] = []
    covered_blocks: dict[str, int] = {}
    for spec in TARGET_BLOCKS:
        block_range = _block_slice(lines, spec)
        if block_range is None:
            continue
        start_idx, end_idx = block_range
        covered_blocks[spec.entry_head] = end_idx - start_idx
        pairs.extend(
            _extract_pairs_from_block(
                lines=lines[start_idx:end_idx],
                spec=spec,
                source_path=source_path,
                nlp=nlp,
            )
        )
    deduped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in pairs:
        key = (
            str(row.get("entry_head") or ""),
            str(row.get("notation_text") or ""),
            str(row.get("context_text") or ""),
        )
        deduped[key] = row
    out_rows = list(deduped.values())
    report = {
        "pipeline_version": "oxford_targeted_note_context_v1",
        "payload_txt": str(Path(payload_txt).resolve()),
        "pairs_total": len(out_rows),
        "topic_counts": {
            spec.topic_key: sum(1 for row in out_rows if row.get("topic_key") == spec.topic_key)
            for spec in TARGET_BLOCKS
            if any(row.get("topic_key") == spec.topic_key for row in out_rows)
        },
        "covered_blocks": covered_blocks,
    }
    return out_rows, report


def main() -> None:
    parser = argparse.ArgumentParser(description="Build targeted note-context pairs from Oxford Dictionary entries.")
    parser.add_argument("--payload-txt", required=True)
    parser.add_argument("--source-path", default="")
    parser.add_argument("--output-jsonl", required=True)
    parser.add_argument("--report-json", required=True)
    parser.add_argument("--spacy-model", default="en_core_web_sm")
    args = parser.parse_args()

    rows, report = build_oxford_targeted_note_context_pairs(
        payload_txt=args.payload_txt,
        source_path=args.source_path,
        spacy_model=args.spacy_model,
    )
    _write_jsonl(args.output_jsonl, rows)
    _write_json(args.report_json, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
