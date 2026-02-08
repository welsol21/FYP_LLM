"""Corpus normalization helpers."""

from __future__ import annotations

import argparse
import json
import re
from typing import Dict, Iterable, List


def normalize_text(text: str) -> str:
    text = text.replace("\u00a0", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_rows(rows: Iterable[Dict]) -> List[Dict]:
    out = []
    for idx, row in enumerate(rows):
        text = normalize_text(str(row.get("text", "")))
        if not text:
            continue
        out.append(
            {
                "id": row.get("id", f"sent_{idx:07d}"),
                "text": text,
                "cefr_level": row.get("cefr_level", "unknown"),
            }
        )
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize corpus rows")
    parser.add_argument("--input", required=True, help="JSON file with list of rows")
    parser.add_argument("--output", required=True, help="Output JSON file")
    args = parser.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        rows = json.load(f)

    normalized = normalize_rows(rows)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(normalized, f, ensure_ascii=False, indent=2)

    print(f"Normalized rows: {len(normalized)}")


if __name__ == "__main__":
    main()
