from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ela_pipeline.classifier.ud_phase1 import load_ud_conllu


TREEBANK_CONFIGS: dict[str, dict[str, Any]] = {
    "UD_English-EWT": {
        "treebank_dir": "data/external_datasets/UD_English-EWT",
        "source_name": "ud_ewt_treebank",
        "source_url": "https://universaldependencies.org/treebanks/en_ewt/index.html",
        "license": "CC BY-SA 4.0",
        "attribution_required": True,
        "id_prefix": "udewt",
    },
    "UD_English-GUM": {
        "treebank_dir": "data/external_datasets/UD_English-GUM",
        "source_name": "ud_gum_treebank",
        "source_url": "https://universaldependencies.org/treebanks/en_gum/index.html",
        "license": "See treebank package license",
        "attribution_required": True,
        "id_prefix": "udgum",
    },
}


def _resolve_split_map(treebank_dir: str) -> dict[str, Path]:
    root = Path(treebank_dir)
    split_map: dict[str, Path] = {}
    for split in ("train", "dev", "test"):
        matches = sorted(root.glob(f"*-ud-{split}.conllu"))
        if not matches:
            raise FileNotFoundError(f"Missing UD split file '*-ud-{split}.conllu' in {treebank_dir}")
        split_map[split] = matches[0]
    return split_map


def build_ud_raw_sentence_corpus(
    *,
    treebanks: list[str],
    output_jsonl: str,
    report_json: str,
    min_chars: int = 12,
    max_chars: int = 320,
) -> dict[str, Any]:
    timestamp = datetime.now(timezone.utc).isoformat()
    out_path = Path(output_jsonl)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    report_path = Path(report_json)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    seen_texts: set[str] = set()
    duplicate_rows = 0
    filtered_short = 0
    filtered_long = 0
    per_treebank_counts: Counter[str] = Counter()
    per_split_counts: Counter[str] = Counter()
    per_genre_counts: Counter[str] = Counter()

    for treebank in treebanks:
        cfg = TREEBANK_CONFIGS.get(treebank)
        if cfg is None:
            raise KeyError(f"Unknown treebank: {treebank}")
        split_map = _resolve_split_map(str(cfg["treebank_dir"]))
        for split, input_path in split_map.items():
            sentences = load_ud_conllu(input_path=str(input_path), treebank=treebank, split=split)
            for sentence in sentences:
                text = str(sentence.get("text") or "").strip()
                if len(text) < min_chars:
                    filtered_short += 1
                    continue
                if len(text) > max_chars:
                    filtered_long += 1
                    continue
                text_key = " ".join(text.split()).lower()
                if text_key in seen_texts:
                    duplicate_rows += 1
                    continue
                seen_texts.add(text_key)
                provenance = sentence.get("provenance") if isinstance(sentence.get("provenance"), dict) else {}
                genre = str(provenance.get("genre") or "").strip().lower()
                sent_id = str(provenance.get("sent_id") or "").strip()
                row_id = f"{cfg['id_prefix']}_{split}_{sent_id or len(rows)}"
                rows.append(
                    {
                        "id": row_id,
                        "text": text,
                        "source_name": cfg["source_name"],
                        "source_url": cfg["source_url"],
                        "license": cfg["license"],
                        "attribution_required": bool(cfg["attribution_required"]),
                        "collected_at": timestamp,
                        "treebank": treebank,
                        "split": split,
                        "genre": genre,
                        "sent_id": sent_id,
                        "doc_id": str(provenance.get("doc_id") or "").strip(),
                        "source_path": str(provenance.get("source_path") or "").strip(),
                    }
                )
                per_treebank_counts[treebank] += 1
                per_split_counts[split] += 1
                if genre:
                    per_genre_counts[genre] += 1

    with out_path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    report = {
        "output_jsonl": str(out_path),
        "treebanks": treebanks,
        "rows_written": len(rows),
        "duplicate_rows": duplicate_rows,
        "filtered_short": filtered_short,
        "filtered_long": filtered_long,
        "min_chars": min_chars,
        "max_chars": max_chars,
        "per_treebank_counts": dict(sorted(per_treebank_counts.items())),
        "per_split_counts": dict(sorted(per_split_counts.items())),
        "per_genre_counts": dict(sorted(per_genre_counts.items())),
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Build raw sentence corpus JSONL from local UD treebanks.")
    parser.add_argument("--treebank", action="append", default=[])
    parser.add_argument("--output-jsonl", required=True)
    parser.add_argument("--report-json", required=True)
    parser.add_argument("--min-chars", type=int, default=12)
    parser.add_argument("--max-chars", type=int, default=320)
    args = parser.parse_args()

    treebanks = args.treebank or ["UD_English-EWT", "UD_English-GUM"]
    report = build_ud_raw_sentence_corpus(
        treebanks=treebanks,
        output_jsonl=args.output_jsonl,
        report_json=args.report_json,
        min_chars=args.min_chars,
        max_chars=args.max_chars,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
