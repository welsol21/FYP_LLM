"""Extract Sentence/Phrase/Word datasets from ingested sentence corpus."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

from ela_pipeline.parse.spacy_parser import load_nlp
from ela_pipeline.skeleton.builder import build_skeleton


def _iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def _base_record(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "source_name": row.get("source_name"),
        "source_url": row.get("source_url"),
        "license": row.get("license"),
        "attribution_required": bool(row.get("attribution_required", True)),
        "collected_at": row.get("collected_at"),
        "parent_sentence_id": row.get("id"),
    }


def _sentence_record(node: Dict[str, Any], base: Dict[str, Any], sentence_text: str) -> Dict[str, Any]:
    out = {
        "node_type": "Sentence",
        "sentence_text": sentence_text,
        "content": node.get("content"),
        "part_of_speech": node.get("part_of_speech"),
        "grammatical_role": node.get("grammatical_role"),
        "dep_label": None,
        "features": {},
        "tense": node.get("tense"),
        "aspect": node.get("aspect"),
        "mood": node.get("mood"),
        "voice": node.get("voice"),
        "finiteness": node.get("finiteness"),
        "node_id": node.get("node_id"),
    }
    out.update(base)
    return out


def _phrase_record(node: Dict[str, Any], base: Dict[str, Any], sentence_text: str) -> Dict[str, Any]:
    out = {
        "node_type": "Phrase",
        "sentence_text": sentence_text,
        "content": node.get("content"),
        "part_of_speech": node.get("part_of_speech"),
        "grammatical_role": node.get("grammatical_role"),
        "dep_label": None,
        "features": {},
        "tense": node.get("tense"),
        "aspect": node.get("aspect"),
        "mood": node.get("mood"),
        "voice": node.get("voice"),
        "finiteness": node.get("finiteness"),
        "node_id": node.get("node_id"),
    }
    out.update(base)
    return out


def _word_record(node: Dict[str, Any], base: Dict[str, Any], sentence_text: str) -> Dict[str, Any]:
    out = {
        "node_type": "Word",
        "sentence_text": sentence_text,
        "content": node.get("content"),
        "part_of_speech": node.get("part_of_speech"),
        "grammatical_role": node.get("grammatical_role"),
        "dep_label": node.get("dep_label"),
        "features": node.get("features") or {},
        "tense": node.get("tense"),
        "aspect": node.get("aspect"),
        "mood": node.get("mood"),
        "voice": node.get("voice"),
        "finiteness": node.get("finiteness"),
        "node_id": node.get("node_id"),
    }
    out.update(base)
    return out


def _write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract sentence/phrase/word datasets from ingested corpus")
    parser.add_argument("--input-jsonl", required=True, help="Ingested sentence corpus JSONL")
    parser.add_argument("--output-dir", required=True, help="Output folder for sentence/phrase/word JSONL")
    parser.add_argument("--spacy-model", default="en_core_web_sm")
    parser.add_argument("--sentence-quota", type=int, default=3000)
    parser.add_argument("--phrase-quota", type=int, default=9000)
    parser.add_argument("--word-quota", type=int, default=18000)
    args = parser.parse_args()

    nlp = load_nlp(args.spacy_model)

    sentence_rows: List[Dict[str, Any]] = []
    phrase_rows: List[Dict[str, Any]] = []
    word_rows: List[Dict[str, Any]] = []
    parse_errors = 0

    for row in _iter_jsonl(Path(args.input_jsonl)):
        if len(sentence_rows) >= int(args.sentence_quota):
            break
        text = str(row.get("text", "")).strip()
        if not text:
            continue
        base = _base_record(row)
        try:
            contract_doc = build_skeleton(text, nlp)
        except Exception:
            parse_errors += 1
            continue
        if not contract_doc:
            continue

        # build_skeleton returns mapping sentence_text -> sentence_node
        for sent_text, sent_node in contract_doc.items():
            if len(sentence_rows) < int(args.sentence_quota):
                sentence_rows.append(_sentence_record(sent_node, base, sent_text))

            for phrase_node in sent_node.get("linguistic_elements", []):
                if len(phrase_rows) < int(args.phrase_quota):
                    phrase_rows.append(_phrase_record(phrase_node, base, sent_text))

                for word_node in phrase_node.get("linguistic_elements", []):
                    if len(word_rows) < int(args.word_quota):
                        word_rows.append(_word_record(word_node, base, sent_text))

            if (
                len(sentence_rows) >= int(args.sentence_quota)
                and len(phrase_rows) >= int(args.phrase_quota)
                and len(word_rows) >= int(args.word_quota)
            ):
                break

        if (
            len(sentence_rows) >= int(args.sentence_quota)
            and len(phrase_rows) >= int(args.phrase_quota)
            and len(word_rows) >= int(args.word_quota)
        ):
            break

    out_dir = Path(args.output_dir)
    _write_jsonl(out_dir / "sentences.jsonl", sentence_rows[: int(args.sentence_quota)])
    _write_jsonl(out_dir / "phrases.jsonl", phrase_rows[: int(args.phrase_quota)])
    _write_jsonl(out_dir / "words.jsonl", word_rows[: int(args.word_quota)])

    report = {
        "input_jsonl": str(args.input_jsonl),
        "spacy_model": args.spacy_model,
        "quotas": {
            "sentence": int(args.sentence_quota),
            "phrase": int(args.phrase_quota),
            "word": int(args.word_quota),
        },
        "saved": {
            "sentence": min(len(sentence_rows), int(args.sentence_quota)),
            "phrase": min(len(phrase_rows), int(args.phrase_quota)),
            "word": min(len(word_rows), int(args.word_quota)),
        },
        "parse_errors": parse_errors,
    }
    (out_dir / "extraction_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
