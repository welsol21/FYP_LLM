"""Build merged full-ladder classifier train/dev/test datasets from accepted source artifacts."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
import random
from typing import Any


def _load_json(path: str) -> dict[str, Any]:
    src = Path(path)
    if not src.is_file():
        raise FileNotFoundError(f"JSON file not found: {path}")
    return json.loads(src.read_text(encoding="utf-8"))


def _load_jsonl(path: str) -> list[dict[str, Any]]:
    src = Path(path)
    if not src.is_file():
        raise FileNotFoundError(f"JSONL file not found: {path}")
    rows: list[dict[str, Any]] = []
    with src.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _normalize_text(value: str) -> str:
    return " ".join(str(value or "").strip().split()).casefold()


def _source_name_from_path(path: str) -> str:
    value = str(path)
    if "gutenberg" in value.lower():
        return "gutenberg"
    if "oanc" in value.lower():
        return "oanc"
    if "pmc" in value.lower():
        return "pmc"
    if "masc" in value.lower():
        return "masc"
    if "gum" in value.lower():
        return "ud_gum"
    if "ewt" in value.lower():
        return "ud_ewt"
    return Path(value).stem


def _extract_dataset_path_from_report(report_path: str) -> str:
    payload = _load_json(report_path)
    if isinstance(payload.get("summary"), dict):
        summary = payload["summary"]
        dataset_path = summary.get("dataset_path")
        if dataset_path:
            return str(dataset_path)
    dataset_path = payload.get("dataset_path")
    if dataset_path:
        return str(dataset_path)
    raise ValueError(f"Could not resolve dataset_path from report: {report_path}")


def _extract_ud_split_paths(summary_path: str) -> dict[str, str]:
    payload = _load_json(summary_path)
    splits = payload.get("splits")
    if not isinstance(splits, dict):
        raise ValueError(f"UD summary missing splits: {summary_path}")
    out: dict[str, str] = {}
    for split in ("train", "dev", "test"):
        node = splits.get(split)
        if not isinstance(node, dict) or not node.get("dataset_path"):
            raise ValueError(f"UD summary missing dataset_path for split '{split}': {summary_path}")
        out[split] = str(node["dataset_path"])
    return out


def _extract_required_train_supports(report_path: str | None) -> dict[tuple[str, str], int]:
    if not report_path:
        return {}
    payload = _load_json(report_path)
    rows = payload.get("advanced_thresholds")
    if not isinstance(rows, list):
        return {}
    out: dict[tuple[str, str], int] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        cefr = str(row.get("cefr_level") or "").strip().upper()
        class_id = str(row.get("class_id") or "").strip().lower()
        required = row.get("required_train_support")
        if cefr and class_id and isinstance(required, int) and required > 0:
            out[(cefr, class_id)] = required
    return out


def _prepare_row(row: dict[str, Any], *, source_name: str) -> dict[str, Any]:
    text = str(row.get("source_text") or row.get("text") or "").strip()
    label = str(row.get("cefr_label") or row.get("cefr_level") or "").strip().upper()
    if not text or not label:
        raise ValueError("Row must include non-empty source_text/text and cefr_label/cefr_level")
    payload = dict(row)
    payload["source_text"] = text
    payload["cefr_label"] = label
    grammar_classes = payload.get("grammar_classes") if isinstance(payload.get("grammar_classes"), list) else []
    grammar_label = "|".join(sorted(str(item).strip().lower() for item in grammar_classes if str(item).strip()))
    if grammar_label:
        payload["grammar_label"] = grammar_label
    provenance = payload.get("provenance") if isinstance(payload.get("provenance"), dict) else {}
    payload["provenance"] = {**provenance, "dataset_source": source_name}
    return payload


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _extract_dep_signature(row: dict[str, Any]) -> set[str]:
    evidence = row.get("grammar_evidence")
    if not isinstance(evidence, dict):
        return set()
    value = evidence.get("dep_signature")
    if not isinstance(value, list):
        return set()
    return {str(item).strip().lower() for item in value if str(item).strip()}


def _extract_token_count(row: dict[str, Any]) -> int:
    evidence = row.get("grammar_evidence")
    if not isinstance(evidence, dict):
        return 0
    value = evidence.get("token_count")
    return int(value) if isinstance(value, int) else 0


def _fails_curriculum_hygiene(row: dict[str, Any]) -> bool:
    label = str(row.get("cefr_label") or "").strip().upper()
    dep_signature = _extract_dep_signature(row)
    token_count = _extract_token_count(row)

    advanced_clause_markers = {
        "ccomp",
        "xcomp",
        "advcl",
        "acl",
        "acl:relcl",
        "parataxis",
        "csubj",
        "csubj:pass",
    }
    if label == "A1":
        return token_count > 12 or bool(dep_signature & advanced_clause_markers)
    if label == "A2":
        return token_count > 18 or bool(dep_signature & {"csubj", "csubj:pass", "parataxis"})
    if label == "B1":
        return token_count > 35 or bool(dep_signature & {"csubj", "csubj:pass"})
    return False


def _split_advanced_rows(
    rows: list[dict[str, Any]],
    *,
    seed: int,
    dev_ratio: float,
    test_ratio: float,
    min_train_support_by_class: dict[tuple[str, str], int] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    if dev_ratio < 0 or test_ratio < 0 or (dev_ratio + test_ratio) >= 1.0:
        raise ValueError("advanced_dev_ratio + advanced_test_ratio must be in [0,1)")

    rng = random.Random(seed)
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        label = str(row.get("cefr_label") or "").upper()
        grammar_classes = row.get("grammar_classes") if isinstance(row.get("grammar_classes"), list) else []
        primary_class = str(grammar_classes[0]).strip().lower() if grammar_classes else ""
        grouped[(label, primary_class)].append(row)

    splits = {"train": [], "dev": [], "test": []}
    min_train_support_by_class = min_train_support_by_class or {}
    for (label, primary_class), label_rows in grouped.items():
        rng.shuffle(label_rows)
        n = len(label_rows)
        if n == 1:
            splits["train"].extend(label_rows)
            continue

        dev_n = int(n * dev_ratio)
        test_n = int(n * test_ratio)
        if dev_ratio > 0 and dev_n == 0 and n >= 3:
            dev_n = 1
        if test_ratio > 0 and test_n == 0 and n >= 5:
            test_n = 1
        while dev_n + test_n >= n:
            if test_n > 0:
                test_n -= 1
            elif dev_n > 0:
                dev_n -= 1
            else:
                break

        required_train = min_train_support_by_class.get((label, primary_class), 0)
        max_holdout = max(0, n - required_train)
        if dev_n + test_n > max_holdout:
            if max_holdout == 0:
                dev_n = 0
                test_n = 0
            else:
                ratio_total = dev_ratio + test_ratio
                if ratio_total > 0:
                    dev_n = int(round(max_holdout * (dev_ratio / ratio_total))) if dev_ratio > 0 else 0
                    test_n = max_holdout - dev_n
                else:
                    dev_n = 0
                    test_n = 0
                if dev_ratio > 0 and test_ratio > 0 and max_holdout >= 2:
                    if dev_n == 0:
                        dev_n = 1
                        test_n = max_holdout - 1
                    if test_n == 0:
                        test_n = 1
                        dev_n = max_holdout - 1

        train_n = n - dev_n - test_n
        train_rows = label_rows[:train_n]
        dev_rows = label_rows[train_n : train_n + dev_n]
        test_rows = label_rows[train_n + dev_n :]
        splits["train"].extend(train_rows)
        splits["dev"].extend(dev_rows)
        splits["test"].extend(test_rows)
    return splits


def build_full_ladder_classifier_dataset(
    *,
    ud_summary_paths: list[str],
    advanced_report_paths: list[str],
    output_dir: str,
    seed: int = 42,
    advanced_dev_ratio: float = 0.1,
    advanced_test_ratio: float = 0.1,
    advanced_threshold_report_path: str | None = None,
) -> dict[str, Any]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    split_rows: dict[str, list[dict[str, Any]]] = {"train": [], "dev": [], "test": []}
    ud_text_index: dict[str, str] = {}
    ud_source_counts: dict[str, Counter[str]] = {"train": Counter(), "dev": Counter(), "test": Counter()}
    curriculum_hygiene_rejections: dict[str, int] = {"train": 0, "dev": 0, "test": 0}

    for summary_path in ud_summary_paths:
        split_map = _extract_ud_split_paths(summary_path)
        for split, dataset_path in split_map.items():
            source_name = _source_name_from_path(summary_path)
            for row in _load_jsonl(dataset_path):
                prepared = _prepare_row(row, source_name=source_name)
                if _fails_curriculum_hygiene(prepared):
                    curriculum_hygiene_rejections[split] += 1
                    continue
                split_rows[split].append(prepared)
                norm = _normalize_text(prepared["source_text"])
                ud_text_index[norm] = split
                ud_source_counts[split][prepared["cefr_label"]] += 1

    advanced_candidates: list[dict[str, Any]] = []
    advanced_ud_collision_rejections = 0
    for report_path in advanced_report_paths:
        dataset_path = _extract_dataset_path_from_report(report_path)
        source_name = _source_name_from_path(report_path)
        for row in _load_jsonl(dataset_path):
            prepared = _prepare_row(row, source_name=source_name)
            norm = _normalize_text(prepared["source_text"])
            if norm in ud_text_index:
                advanced_ud_collision_rejections += 1
                continue
            prepared["_norm_text"] = norm
            advanced_candidates.append(prepared)

    grouped_by_text: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in advanced_candidates:
        grouped_by_text[row["_norm_text"]].append(row)

    advanced_conflicts: list[dict[str, Any]] = []
    advanced_conflict_rejected_rows = 0
    deduped_advanced: list[dict[str, Any]] = []
    for norm_text, rows in grouped_by_text.items():
        labels = {str(row.get("cefr_label") or "").upper() for row in rows}
        if len(labels) > 1:
            advanced_conflict_rejected_rows += len(rows)
            advanced_conflicts.append(
                {
                    "source_text": rows[0].get("source_text"),
                    "normalized_text": norm_text,
                    "labels": sorted(labels),
                    "sources": sorted({str((row.get("provenance") or {}).get("dataset_source") or "") for row in rows}),
                }
            )
            continue
        deduped_advanced.append(rows[0] | {"_norm_text": norm_text})

    advanced_splits = _split_advanced_rows(
        deduped_advanced,
        seed=seed,
        dev_ratio=advanced_dev_ratio,
        test_ratio=advanced_test_ratio,
        min_train_support_by_class=_extract_required_train_supports(advanced_threshold_report_path),
    )
    for split in ("train", "dev", "test"):
        for row in advanced_splits[split]:
            payload = dict(row)
            payload.pop("_norm_text", None)
            split_rows[split].append(payload)

    for split in ("train", "dev", "test"):
        split_rows[split].sort(key=lambda row: (row.get("cefr_label") or "", row.get("source_text") or ""))

    train_path = out_dir / "train_classifier.jsonl"
    dev_path = out_dir / "dev_classifier.jsonl"
    test_path = out_dir / "test_classifier.jsonl"
    rejected_conflicts_path = out_dir / "rejected_advanced_conflicts.jsonl"
    summary_path = out_dir / "full_ladder_dataset_summary.json"

    _write_jsonl(train_path, split_rows["train"])
    _write_jsonl(dev_path, split_rows["dev"])
    _write_jsonl(test_path, split_rows["test"])
    _write_jsonl(rejected_conflicts_path, advanced_conflicts)

    split_cefr_counts = {
        split: dict(sorted(Counter(str(row.get("cefr_label") or "").upper() for row in rows).items()))
        for split, rows in split_rows.items()
    }
    split_grammar_counts = {
        split: dict(sorted(Counter(str(row.get("grammar_label") or "") for row in rows if str(row.get("grammar_label") or "")).items()))
        for split, rows in split_rows.items()
    }
    split_source_counts = {
        split: dict(sorted(Counter(str((row.get("provenance") or {}).get("dataset_source") or "unknown") for row in rows).items()))
        for split, rows in split_rows.items()
    }
    summary = {
        "train_path": str(train_path),
        "dev_path": str(dev_path),
        "test_path": str(test_path),
        "rejected_conflicts_path": str(rejected_conflicts_path),
        "splits": {split: len(rows) for split, rows in split_rows.items()},
        "split_cefr_counts": split_cefr_counts,
        "split_grammar_counts": split_grammar_counts,
        "split_source_counts": split_source_counts,
        "advanced_rows_added": {split: len(advanced_splits[split]) for split in ("train", "dev", "test")},
        "advanced_ud_collision_rejections": advanced_ud_collision_rejections,
        "advanced_conflict_rejections": advanced_conflict_rejected_rows,
        "advanced_conflict_texts": len(advanced_conflicts),
        "advanced_candidate_rows": len(advanced_candidates),
        "advanced_deduped_rows": len(deduped_advanced),
        "curriculum_hygiene_rejections": curriculum_hygiene_rejections,
        "ud_summary_paths": list(ud_summary_paths),
        "advanced_report_paths": list(advanced_report_paths),
        "advanced_threshold_report_path": str(advanced_threshold_report_path or ""),
        "seed": seed,
        "advanced_dev_ratio": advanced_dev_ratio,
        "advanced_test_ratio": advanced_test_ratio,
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Build merged A1-C2 classifier train/dev/test datasets.")
    parser.add_argument(
        "--ud-summary-path",
        action="append",
        required=True,
        help="Path to UD treebank summary JSON. Can be passed multiple times.",
    )
    parser.add_argument(
        "--advanced-report-path",
        action="append",
        required=True,
        help="Path to accepted advanced probe/report JSON. Can be passed multiple times.",
    )
    parser.add_argument("--output-dir", default="artifacts/classifier_full_ladder_dataset")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--advanced-dev-ratio", type=float, default=0.1)
    parser.add_argument("--advanced-test-ratio", type=float, default=0.1)
    parser.add_argument("--advanced-threshold-report-path", default="")
    args = parser.parse_args()

    summary = build_full_ladder_classifier_dataset(
        ud_summary_paths=args.ud_summary_path,
        advanced_report_paths=args.advanced_report_path,
        output_dir=args.output_dir,
        seed=args.seed,
        advanced_dev_ratio=args.advanced_dev_ratio,
        advanced_test_ratio=args.advanced_test_ratio,
        advanced_threshold_report_path=str(args.advanced_threshold_report_path or "").strip() or None,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
