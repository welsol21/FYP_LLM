"""Build a licensed sentence corpus from multiple vetted sources.

The script merges source files into one normalized JSONL corpus with
provenance metadata and deterministic per-source quotas.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from ela_pipeline.corpus.normalize import normalize_text


@dataclass(frozen=True)
class SourceSpec:
    name: str
    input_path: str
    source_url: str
    license: str
    attribution_required: bool
    quota: int
    format: str = "jsonl"  # jsonl | json_array | txt
    text_field: str = "text"
    id_prefix: str = ""


def _normalize_key(text: str) -> str:
    clean = normalize_text(text)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean.lower()


def _iter_rows(spec: SourceSpec) -> Iterable[Tuple[str, str]]:
    path = Path(spec.input_path)
    if not path.exists():
        raise FileNotFoundError(f"Missing source file: {path}")
    if spec.format == "jsonl":
        with path.open("r", encoding="utf-8") as f:
            for idx, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                text = str(row.get(spec.text_field, "")).strip()
                rid = str(row.get("id", f"{spec.id_prefix or spec.name}_{idx:07d}"))
                yield rid, text
        return

    if spec.format == "json_array":
        with path.open("r", encoding="utf-8") as f:
            rows = json.load(f)
        for idx, row in enumerate(rows):
            text = str(row.get(spec.text_field, "")).strip()
            rid = str(row.get("id", f"{spec.id_prefix or spec.name}_{idx:07d}"))
            yield rid, text
        return

    if spec.format == "txt":
        with path.open("r", encoding="utf-8") as f:
            for idx, line in enumerate(f):
                text = line.strip()
                if not text:
                    continue
                rid = f"{spec.id_prefix or spec.name}_{idx:07d}"
                yield rid, text
        return

    raise ValueError(f"Unsupported format: {spec.format}")


def _load_specs(path: Path) -> List[SourceSpec]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    specs: List[SourceSpec] = []
    for item in raw.get("sources", []):
        specs.append(
            SourceSpec(
                name=str(item["name"]),
                input_path=str(item["input_path"]),
                source_url=str(item["source_url"]),
                license=str(item["license"]),
                attribution_required=bool(item.get("attribution_required", True)),
                quota=int(item["quota"]),
                format=str(item.get("format", "jsonl")),
                text_field=str(item.get("text_field", "text")),
                id_prefix=str(item.get("id_prefix", "")),
            )
        )
    if not specs:
        raise ValueError("Config has no sources")
    return specs


def _is_text_eligible(text: str, min_chars: int, max_chars: int) -> bool:
    if not text:
        return False
    n = len(text)
    if n < min_chars or n > max_chars:
        return False
    return True


def build_corpus(
    specs: List[SourceSpec],
    min_chars: int,
    max_chars: int,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    seen = set()
    out: List[Dict[str, Any]] = []
    stats: Dict[str, Any] = {
        "total_rows": 0,
        "kept_rows": 0,
        "dropped_duplicates": 0,
        "dropped_length": 0,
        "by_source": {},
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    for spec in specs:
        source_total = 0
        source_kept = 0
        source_drop_dup = 0
        source_drop_len = 0
        for rid, raw_text in _iter_rows(spec):
            source_total += 1
            text = normalize_text(raw_text)
            if not _is_text_eligible(text, min_chars=min_chars, max_chars=max_chars):
                source_drop_len += 1
                continue
            key = _normalize_key(text)
            if key in seen:
                source_drop_dup += 1
                continue
            record = {
                "id": rid,
                "text": text,
                "source_name": spec.name,
                "source_url": spec.source_url,
                "license": spec.license,
                "attribution_required": spec.attribution_required,
                "collected_at": stats["generated_at"],
            }
            out.append(record)
            seen.add(key)
            source_kept += 1
            if source_kept >= spec.quota:
                break

        stats["by_source"][spec.name] = {
            "quota": spec.quota,
            "read_rows": source_total,
            "kept_rows": source_kept,
            "dropped_duplicates": source_drop_dup,
            "dropped_length": source_drop_len,
        }
        stats["total_rows"] += source_total
        stats["kept_rows"] += source_kept
        stats["dropped_duplicates"] += source_drop_dup
        stats["dropped_length"] += source_drop_len

    return out, stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Build licensed ingestion corpus (JSONL)")
    parser.add_argument("--config", required=True, help="JSON config with source list and quotas")
    parser.add_argument("--output-jsonl", required=True, help="Output JSONL path")
    parser.add_argument("--report-json", required=True, help="Output quality report JSON path")
    parser.add_argument("--min-chars", type=int, default=12, help="Minimum sentence length")
    parser.add_argument("--max-chars", type=int, default=260, help="Maximum sentence length")
    args = parser.parse_args()

    specs = _load_specs(Path(args.config))
    missing = [s.input_path for s in specs if not Path(s.input_path).exists()]
    if missing:
        raise SystemExit(
            "Missing source files for ingestion:\n- "
            + "\n- ".join(missing)
            + "\nPrepare data/raw_sources/*.jsonl before running this command."
        )
    rows, stats = build_corpus(specs, min_chars=int(args.min_chars), max_chars=int(args.max_chars))

    out_path = Path(args.output_jsonl)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    report_path = Path(args.report_json)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Saved rows: {len(rows)}")
    print(f"Saved report: {report_path}")


if __name__ == "__main__":
    main()
