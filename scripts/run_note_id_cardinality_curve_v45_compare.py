from __future__ import annotations

import argparse
import hashlib
import json
import random
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import cupy as cp
import joblib
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ela_pipeline.classifier.infer_tabular_note_classifier import _resolve_note_id
from ela_pipeline.classifier.train_tabular_cefr_baseline import build_feature_rows, train_tabular_cefr_baseline


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _note_id(text: str) -> str:
    return f"note_{hashlib.sha1(text.encode('utf-8')).hexdigest()[:12]}"


def _build_rows_from_mixed(all_path: Path, *, mode: str) -> list[dict[str, Any]]:
    rows = _load_jsonl(all_path)
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        input_text = str(row.get("input") or "").strip()
        note_text = str(row.get("target") or "").strip()
        if not input_text or not note_text:
            continue
        is_template = "{{" in note_text
        if mode == "raw" and is_template:
            continue
        if mode == "template" and not is_template:
            continue
        note_id = _note_id(note_text)
        key = (input_text, note_id)
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "input": input_text,
                "text": input_text,
                "source_text": input_text,
                "note_id": note_id,
                "note_text": note_text,
                "note_type": mode,
                "dataset_name": f"v45_{mode}",
                "grammar_evidence": {},
                "grammar_classes": [],
                "provenance": {
                    "dataset_source": f"note_id_curve_v45_{mode}",
                    "treebank": f"v45_{mode}",
                },
            }
        )
    return out


def _stratified_split(
    rows: list[dict[str, Any]],
    *,
    seed: int,
    dev_ratio: float,
    test_ratio: float,
) -> dict[str, list[dict[str, Any]]]:
    by_label: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_label[str(row.get("note_id") or "")].append(dict(row))

    rng = random.Random(seed)
    split_rows = {"train": [], "dev": [], "test": []}
    for label, items in by_label.items():
        rng.shuffle(items)
        n = len(items)
        test_n = max(1, int(round(n * test_ratio)))
        dev_n = max(1, int(round(n * dev_ratio)))
        if test_n + dev_n >= n:
            test_n = 1
            dev_n = 1
        train_n = n - dev_n - test_n
        if train_n < 1:
            train_n = 1
            if dev_n > test_n:
                dev_n -= 1
            else:
                test_n -= 1
        train_items = items[:train_n]
        dev_items = items[train_n:train_n + dev_n]
        test_items = items[train_n + dev_n:train_n + dev_n + test_n]
        for split_name, subset in (("train", train_items), ("dev", dev_items), ("test", test_items)):
            for row in subset:
                row["split_name"] = split_name
                split_rows[split_name].append(row)
    return split_rows


def _write_subset_dir(subset_dir: Path, split_rows: dict[str, list[dict[str, Any]]]) -> None:
    for split_name, rows in split_rows.items():
        _write_jsonl(subset_dir / f"{split_name}.jsonl", rows)
    all_rows = split_rows["train"] + split_rows["dev"] + split_rows["test"]
    _write_jsonl(subset_dir / "all.jsonl", all_rows)


def _evaluate_topk(*, dataset_path: Path, model_path: Path, summary_path: Path) -> dict[str, Any]:
    rows = _load_jsonl(dataset_path)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    feature_profile = str(summary.get("feature_profile") or "runtime_stable")
    label_order = [str(item) for item in summary.get("label_order") or [] if str(item).strip()]

    model = joblib.load(model_path)
    vectorizer = model.named_steps["vectorizer"]
    classifier = model.named_steps["classifier"]
    booster = classifier.get_booster()
    classes = list(getattr(classifier, "classes_", []))

    feature_rows, labels = build_feature_rows(rows, label_field="note_id", feature_profile=feature_profile)
    X_np = vectorizer.transform(feature_rows).astype(np.float32, copy=False)
    X_cp = cp.asarray(X_np)
    proba = cp.asnumpy(booster.inplace_predict(X_cp))

    top1_hits = 0
    top3_hits = 0
    top5_hits = 0
    margins = []
    correct_scores = []
    wrong_scores = []
    for gold, scores in zip(labels, proba):
        order = np.argsort(scores)[::-1]
        preds = [
            _resolve_note_id(classes[int(i)] if int(i) < len(classes) else int(i), label_order=label_order)
            for i in order[:5]
        ]
        s1 = float(scores[int(order[0])])
        s2 = float(scores[int(order[1])]) if len(order) > 1 else 0.0
        margins.append(s1 - s2)
        hit1 = preds[0] == gold
        top1_hits += int(hit1)
        top3_hits += int(gold in preds[:3])
        top5_hits += int(gold in preds[:5])
        if hit1:
            correct_scores.append(s1)
        else:
            wrong_scores.append(s1)

    n = len(labels)
    return {
        "samples": n,
        "top1_accuracy": top1_hits / n if n else 0.0,
        "top3_accuracy": top3_hits / n if n else 0.0,
        "top5_accuracy": top5_hits / n if n else 0.0,
        "avg_top1_score": statistics.mean(float(np.max(s)) for s in proba) if n else 0.0,
        "avg_margin_top1_top2": statistics.mean(margins) if margins else 0.0,
        "avg_top1_score_when_correct": statistics.mean(correct_scores) if correct_scores else 0.0,
        "avg_top1_score_when_wrong": statistics.mean(wrong_scores) if wrong_scores else 0.0,
        "inference_backend": "xgboost_inplace_predict_cupy",
    }


def _run_mode(
    *,
    mixed_all_path: Path,
    mode: str,
    checkpoints: list[int],
    min_support: int,
    working_dir: Path,
    seed: int,
    dev_ratio: float,
    test_ratio: float,
    feature_profile: str,
) -> dict[str, Any]:
    all_rows = _build_rows_from_mixed(mixed_all_path, mode=mode)
    support = Counter(str(row.get("note_id") or "") for row in all_rows)
    eligible_ids = [note_id for note_id, count in sorted(support.items(), key=lambda item: (-item[1], item[0])) if count >= min_support]

    results: list[dict[str, Any]] = []
    for note_count in checkpoints:
        allowed = set(eligible_ids[:note_count])
        subset_rows = [row for row in all_rows if str(row.get("note_id") or "") in allowed]
        split_rows = _stratified_split(subset_rows, seed=seed, dev_ratio=dev_ratio, test_ratio=test_ratio)
        subset_dir = working_dir / mode / f"subset_{note_count:03d}"
        _write_subset_dir(subset_dir, split_rows)
        subset_stats = {
            "unique_note_ids": note_count,
            "train_samples": len(split_rows["train"]),
            "dev_samples": len(split_rows["dev"]),
            "test_samples": len(split_rows["test"]),
            "all_samples": len(subset_rows),
        }
        model_dir = working_dir / mode / f"model_{note_count:03d}"
        summary = train_tabular_cefr_baseline(
            train_path=str(subset_dir / "train.jsonl"),
            dev_path=str(subset_dir / "dev.jsonl"),
            test_path=str(subset_dir / "test.jsonl"),
            output_dir=str(model_dir),
            model_names=["xgboost_gpu"],
            seed=seed,
            label_field="note_id",
            feature_profile=feature_profile,
        )
        test_metrics = _evaluate_topk(
            dataset_path=subset_dir / "test.jsonl",
            model_path=model_dir / "best_tabular_cefr_baseline.joblib",
            summary_path=model_dir / "tabular_cefr_baseline_summary.json",
        )
        row = {
            "unique_note_ids": note_count,
            "subset_stats": subset_stats,
            "dev_accuracy": float(summary["models"]["xgboost_gpu"]["dev"]["accuracy"]),
            "dev_macro_f1": float(summary["models"]["xgboost_gpu"]["dev"]["macro_f1"]),
            "test_accuracy_argmax": float(summary["models"]["xgboost_gpu"]["test"]["accuracy"]),
            "test_macro_f1": float(summary["models"]["xgboost_gpu"]["test"]["macro_f1"]),
            "test_metrics": test_metrics,
        }
        results.append(row)
        print(json.dumps({"mode": mode, **row}, ensure_ascii=False))

    return {
        "mode": mode,
        "eligible_note_ids": len(eligible_ids),
        "min_support": min_support,
        "results": results,
    }


def _plot_compare(report: dict[str, Any], *, output_path: Path) -> None:
    plt.figure(figsize=(10, 6))
    for metric, linestyle in (("top1_accuracy", "-"), ("top3_accuracy", "--")):
        for mode, color in (("raw", "#1b6ca8"), ("template", "#c1582a")):
            results = report[mode]["results"]
            x = [int(row["unique_note_ids"]) for row in results]
            y = [float(row["test_metrics"][metric]) for row in results]
            plt.plot(x, y, marker="o", linestyle=linestyle, color=color, label=f"{mode} {metric.replace('_', ' ')}")
    plt.xlabel("Unique note_ids")
    plt.ylabel("Metric")
    plt.title("v45 Raw vs Template Note-ID Curves")
    plt.grid(True, alpha=0.25)
    plt.legend()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(output_path, dpi=160)
    plt.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare raw vs templated note_id curves on v45 mixed dataset.")
    parser.add_argument(
        "--mixed-all-path",
        default="data/processed_sentence_seed/seed_preserving_sentence_dataset_v45_paired_template_sentence_nodes_contractfix4_v1/all.jsonl",
    )
    parser.add_argument("--working-dir", default="artifacts/note_id_cardinality_curve_v45_compare_v1")
    parser.add_argument("--start-note-count", type=int, default=58)
    parser.add_argument("--step", type=int, default=15)
    parser.add_argument("--min-support", type=int, default=3)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dev-ratio", type=float, default=0.15)
    parser.add_argument("--test-ratio", type=float, default=0.15)
    parser.add_argument("--feature-profile", default="runtime_stable", choices=["full", "no_source", "runtime_stable"])
    args = parser.parse_args()

    mixed_all_path = Path(args.mixed_all_path)
    raw_rows = _build_rows_from_mixed(mixed_all_path, mode="raw")
    template_rows = _build_rows_from_mixed(mixed_all_path, mode="template")
    raw_support = Counter(str(row.get("note_id") or "") for row in raw_rows)
    templ_support = Counter(str(row.get("note_id") or "") for row in template_rows)
    raw_eligible = [note_id for note_id, count in raw_support.items() if count >= args.min_support]
    templ_eligible = [note_id for note_id, count in templ_support.items() if count >= args.min_support]
    common_max = min(len(raw_eligible), len(templ_eligible))
    checkpoints: list[int] = []
    current = args.start_note_count
    while current < common_max:
        checkpoints.append(current)
        current += args.step
    if common_max not in checkpoints:
        checkpoints.append(common_max)

    working_dir = Path(args.working_dir)
    raw_report = _run_mode(
        mixed_all_path=mixed_all_path,
        mode="raw",
        checkpoints=checkpoints,
        min_support=args.min_support,
        working_dir=working_dir,
        seed=args.seed,
        dev_ratio=args.dev_ratio,
        test_ratio=args.test_ratio,
        feature_profile=args.feature_profile,
    )
    template_report = _run_mode(
        mixed_all_path=mixed_all_path,
        mode="template",
        checkpoints=checkpoints,
        min_support=args.min_support,
        working_dir=working_dir,
        seed=args.seed,
        dev_ratio=args.dev_ratio,
        test_ratio=args.test_ratio,
        feature_profile=args.feature_profile,
    )

    report = {
        "experiment": "note_id_cardinality_curve_v45_compare_v1",
        "mixed_all_path": str(mixed_all_path.resolve()),
        "feature_profile": args.feature_profile,
        "start_note_count": args.start_note_count,
        "step": args.step,
        "min_support": args.min_support,
        "common_checkpoints": checkpoints,
        "raw": raw_report,
        "template": template_report,
    }
    working_dir.mkdir(parents=True, exist_ok=True)
    (working_dir / "compare_results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["mode,unique_note_ids,train_samples,dev_samples,test_samples,dev_accuracy,dev_macro_f1,test_accuracy_argmax,test_macro_f1,test_top1,test_top3,test_top5"]
    for mode in ("raw", "template"):
        for row in report[mode]["results"]:
            lines.append(
                ",".join(
                    [
                        mode,
                        str(int(row["unique_note_ids"])),
                        str(int(row["subset_stats"]["train_samples"])),
                        str(int(row["subset_stats"]["dev_samples"])),
                        str(int(row["subset_stats"]["test_samples"])),
                        f"{row['dev_accuracy']:.6f}",
                        f"{row['dev_macro_f1']:.6f}",
                        f"{row['test_accuracy_argmax']:.6f}",
                        f"{row['test_macro_f1']:.6f}",
                        f"{row['test_metrics']['top1_accuracy']:.6f}",
                        f"{row['test_metrics']['top3_accuracy']:.6f}",
                        f"{row['test_metrics']['top5_accuracy']:.6f}",
                    ]
                )
            )
    (working_dir / "compare_results.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    _plot_compare(report, output_path=working_dir / "compare_metrics.png")


if __name__ == "__main__":
    main()
