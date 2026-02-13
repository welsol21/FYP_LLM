"""Quality report for ingested sentence/phrase/word datasets."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable


def _iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def _norm_text(s: str) -> str:
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s.lower()


def main() -> None:
    parser = argparse.ArgumentParser(description="Build quality report for ingestion pipeline outputs")
    parser.add_argument("--ingested-jsonl", required=True)
    parser.add_argument("--nodes-dir", required=True, help="Directory with sentences.jsonl/phrases.jsonl/words.jsonl")
    parser.add_argument("--output-json", required=True)
    args = parser.parse_args()

    ingested_path = Path(args.ingested_jsonl)
    nodes_dir = Path(args.nodes_dir)

    ingested_rows = list(_iter_jsonl(ingested_path))
    sentences = list(_iter_jsonl(nodes_dir / "sentences.jsonl"))
    phrases = list(_iter_jsonl(nodes_dir / "phrases.jsonl"))
    words = list(_iter_jsonl(nodes_dir / "words.jsonl"))

    source_counts = Counter()
    license_missing = 0
    source_missing = 0
    seen_norm = set()
    dup = 0
    for row in ingested_rows:
        source_name = str(row.get("source_name", "")).strip()
        if not source_name:
            source_missing += 1
        source_counts[source_name or "MISSING"] += 1
        if not str(row.get("license", "")).strip():
            license_missing += 1
        key = _norm_text(row.get("text", ""))
        if key in seen_norm:
            dup += 1
        else:
            seen_norm.add(key)

    pos_counts = Counter()
    dep_counts = Counter()
    tam_counts = Counter()
    level_counts = {"Sentence": len(sentences), "Phrase": len(phrases), "Word": len(words)}

    for row in phrases + words + sentences:
        pos = str(row.get("part_of_speech", "")).strip() or "unknown"
        pos_counts[pos] += 1
        dep = str(row.get("dep_label", "")).strip() or "none"
        dep_counts[dep] += 1
        tense = str(row.get("tense", "null"))
        aspect = str(row.get("aspect", "null"))
        mood = str(row.get("mood", "null"))
        voice = str(row.get("voice", "null"))
        fin = str(row.get("finiteness", "null"))
        tam_counts[f"tense={tense}|aspect={aspect}|mood={mood}|voice={voice}|finiteness={fin}"] += 1

    extraction_report = {}
    ext_report_path = nodes_dir / "extraction_report.json"
    if ext_report_path.exists():
        extraction_report = json.loads(ext_report_path.read_text(encoding="utf-8"))

    report = {
        "paths": {
            "ingested_jsonl": str(ingested_path),
            "nodes_dir": str(nodes_dir),
        },
        "counts": {
            "ingested_rows": len(ingested_rows),
            "sentences": len(sentences),
            "phrases": len(phrases),
            "words": len(words),
            "duplicate_sentences_norm": dup,
            "duplicate_ratio_norm": (dup / len(ingested_rows)) if ingested_rows else 0.0,
        },
        "license_coverage": {
            "missing_license_rows": license_missing,
            "missing_source_rows": source_missing,
            "license_coverage_ratio": (1 - license_missing / len(ingested_rows)) if ingested_rows else 0.0,
        },
        "per_source_contribution": dict(sorted(source_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
        "distributions": {
            "level": level_counts,
            "part_of_speech_top20": dict(pos_counts.most_common(20)),
            "dep_label_top20": dict(dep_counts.most_common(20)),
            "tam_top20": dict(tam_counts.most_common(20)),
        },
        "parse_quality": {
            "parse_errors": extraction_report.get("parse_errors"),
            "quotas": extraction_report.get("quotas"),
            "saved": extraction_report.get("saved"),
        },
    }

    out_path = Path(args.output_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
