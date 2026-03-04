"""Genre-aware advanced coverage reporting for UD_English-GUM."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .ud_phase1 import extract_phase1_grammar_signal, load_ud_conllu

DEFAULT_ADVANCED_GENRES = ("academic", "court", "speech", "textbook", "essay", "news")
ADVANCED_CLASSES = {"past_perfect", "passive_voice", "modal_perfect", "future_perfect"}


def build_gum_genre_advanced_report(
    *,
    treebank_dir: str,
    genres: list[str] | tuple[str, ...] = DEFAULT_ADVANCED_GENRES,
) -> dict[str, Any]:
    root = Path(treebank_dir)
    if not root.is_dir():
        raise FileNotFoundError(f"treebank_dir not found: {treebank_dir}")

    wanted = {str(value).strip().lower() for value in genres if str(value).strip()}
    split_map = {
        split: next(iter(sorted(root.glob(f"*-ud-{split}.conllu"))), None)
        for split in ("train", "dev", "test")
    }
    if not all(split_map.values()):
        missing = [split for split, path in split_map.items() if path is None]
        raise FileNotFoundError(f"Missing GUM split files for: {', '.join(missing)}")

    split_rows: dict[str, list[dict[str, Any]]] = {}
    for split, path in split_map.items():
        split_rows[split] = load_ud_conllu(
            input_path=str(path),
            treebank="UD_English-GUM",
            split=split,
        )

    per_genre_split: dict[str, Counter[str]] = defaultdict(Counter)
    per_genre_class_support: dict[str, Counter[tuple[str, str]]] = defaultdict(Counter)
    total_by_genre: Counter[str] = Counter()
    selected_by_genre: Counter[str] = Counter()

    for split, rows in split_rows.items():
        for row in rows:
            provenance = row.get("provenance") if isinstance(row.get("provenance"), dict) else {}
            genre = str(provenance.get("genre") or "").strip().lower()
            if not genre:
                continue
            total_by_genre[genre] += 1
            if wanted and genre not in wanted:
                continue
            signal = extract_phase1_grammar_signal(row)
            grammar_classes = [class_id for class_id in signal.get("grammar_classes", []) if class_id in ADVANCED_CLASSES]
            if not grammar_classes:
                continue
            selected_by_genre[genre] += 1
            for class_id in grammar_classes:
                cefr = "B2"
                if class_id == "modal_perfect":
                    cefr = "C1"
                elif class_id == "future_perfect":
                    cefr = "C2"
                per_genre_split[genre][split] += 1
                per_genre_class_support[genre][(cefr, class_id)] += 1

    genre_rows: list[dict[str, Any]] = []
    aggregate_support: Counter[tuple[str, str]] = Counter()
    for genre in sorted(wanted):
        class_rows = []
        for (cefr, class_id), count in sorted(per_genre_class_support.get(genre, Counter()).items()):
            class_rows.append({"cefr_level": cefr, "class_id": class_id, "count": count})
            aggregate_support[(cefr, class_id)] += count
        genre_rows.append(
            {
                "genre": genre,
                "total_sentences": total_by_genre.get(genre, 0),
                "advanced_sentences": selected_by_genre.get(genre, 0),
                "split_counts": dict(sorted(per_genre_split.get(genre, Counter()).items())),
                "class_support": class_rows,
            }
        )

    aggregate_rows = [
        {"cefr_level": cefr, "class_id": class_id, "count": count}
        for (cefr, class_id), count in sorted(aggregate_support.items())
    ]

    return {
        "treebank": "UD_English-GUM",
        "treebank_dir": str(root),
        "selected_genres": sorted(wanted),
        "genres": genre_rows,
        "aggregate_class_support": aggregate_rows,
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Build genre-aware advanced coverage report for UD_English-GUM.")
    parser.add_argument("--treebank-dir", required=True)
    parser.add_argument("--genre", action="append", default=[])
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    report = build_gum_genre_advanced_report(
        treebank_dir=args.treebank_dir,
        genres=args.genre or list(DEFAULT_ADVANCED_GENRES),
    )
    if str(args.output or "").strip():
        Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
