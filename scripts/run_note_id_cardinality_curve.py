from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter
from pathlib import Path
import sys
from typing import Any

import cupy as cp
import joblib
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ela_pipeline.classifier.build_note_id_classifier_dataset_from_contract_candidates import build_dataset
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


def _ensure_train_covers_all_note_ids(split_rows: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
    train_ids = {str(row.get("note_id") or "") for row in split_rows["train"]}
    moved_from_dev = 0
    moved_from_test = 0
    for split_name in ("dev", "test"):
        remaining: list[dict[str, Any]] = []
        for row in split_rows[split_name]:
            note_id = str(row.get("note_id") or "")
            if note_id and note_id not in train_ids:
                promoted = dict(row)
                promoted["split_name"] = "train"
                split_rows["train"].append(promoted)
                train_ids.add(note_id)
                if split_name == "dev":
                    moved_from_dev += 1
                else:
                    moved_from_test += 1
                continue
            remaining.append(row)
        split_rows[split_name] = remaining
    return {
        "promoted_note_id_rows_from_dev_to_train": moved_from_dev,
        "promoted_note_id_rows_from_test_to_train": moved_from_test,
    }


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
        hit3 = gold in preds[:3]
        hit5 = gold in preds[:5]
        top1_hits += int(hit1)
        top3_hits += int(hit3)
        top5_hits += int(hit5)
        if hit1:
            correct_scores.append(s1)
        else:
            wrong_scores.append(s1)

    count = len(labels)
    return {
        "samples": count,
        "top1_accuracy": top1_hits / count if count else 0.0,
        "top3_accuracy": top3_hits / count if count else 0.0,
        "top5_accuracy": top5_hits / count if count else 0.0,
        "avg_top1_score": statistics.mean(float(np.max(s)) for s in proba) if count else 0.0,
        "avg_margin_top1_top2": statistics.mean(margins) if margins else 0.0,
        "avg_top1_score_when_correct": statistics.mean(correct_scores) if correct_scores else 0.0,
        "avg_top1_score_when_wrong": statistics.mean(wrong_scores) if wrong_scores else 0.0,
        "inference_backend": "xgboost_inplace_predict_cupy",
    }


def _build_subset(
    *,
    full_dir: Path,
    subset_dir: Path,
    allowed_note_ids: set[str],
) -> dict[str, Any]:
    split_rows = {
        split_name: [row for row in _load_jsonl(full_dir / f"{split_name}.jsonl") if str(row.get("note_id") or "") in allowed_note_ids]
        for split_name in ("train", "dev", "test")
    }
    coverage = _ensure_train_covers_all_note_ids(split_rows)
    for split_name, rows in split_rows.items():
        _write_jsonl(subset_dir / f"{split_name}.jsonl", rows)
    all_rows = split_rows["train"] + split_rows["dev"] + split_rows["test"]
    _write_jsonl(subset_dir / "all.jsonl", all_rows)
    present_ids = sorted({str(row.get("note_id") or "") for row in all_rows if str(row.get("note_id") or "")})
    (subset_dir / "note_id_inventory.json").write_text(
        json.dumps(
            [
                {
                    "note_id": note_id,
                    "note_text": next(str(row.get("note_text") or "") for row in all_rows if str(row.get("note_id") or "") == note_id),
                    "note_type": "raw",
                }
                for note_id in present_ids
            ],
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "train_samples": len(split_rows["train"]),
        "dev_samples": len(split_rows["dev"]),
        "test_samples": len(split_rows["test"]),
        "all_samples": len(all_rows),
        "unique_note_ids": len(present_ids),
        **coverage,
    }


def _plot_curve(results: list[dict[str, Any]], *, output_path: Path) -> None:
    x = [int(row["unique_note_ids"]) for row in results]
    top1 = [float(row["test_metrics"]["top1_accuracy"]) for row in results]
    top3 = [float(row["test_metrics"]["top3_accuracy"]) for row in results]
    macro_f1 = [float(row["dev_macro_f1"]) for row in results]

    plt.figure(figsize=(9, 5.5))
    plt.plot(x, top1, marker="o", label="test top-1")
    plt.plot(x, top3, marker="o", label="test top-3")
    plt.plot(x, macro_f1, marker="o", label="dev macro-F1")
    plt.xlabel("Unique note_ids in dataset")
    plt.ylabel("Metric")
    plt.title("Note-ID Classifier vs Note Inventory Size")
    plt.grid(True, alpha=0.25)
    plt.legend()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(output_path, dpi=160)
    plt.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run note_id cardinality curve experiment on contract-input raw-note dataset.")
    parser.add_argument(
        "--input-path",
        default="data/processed_corpus_book_projection_v16/ingested_corpus_book_projection_v16.covered_only.jsonl",
    )
    parser.add_argument(
        "--working-dir",
        default="artifacts/note_id_cardinality_curve_contract_raw_v1",
    )
    parser.add_argument("--start-note-count", type=int, default=58)
    parser.add_argument("--step", type=int, default=15)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dev-ratio", type=float, default=0.1)
    parser.add_argument("--test-ratio", type=float, default=0.1)
    parser.add_argument("--feature-profile", default="runtime_stable", choices=["full", "no_source", "runtime_stable"])
    args = parser.parse_args()

    working_dir = Path(args.working_dir)
    full_dataset_dir = working_dir / "full_dataset"
    full_stats = build_dataset(
        input_path=args.input_path,
        output_dir=str(full_dataset_dir),
        seed=args.seed,
        dev_ratio=args.dev_ratio,
        test_ratio=args.test_ratio,
    )

    all_rows = _load_jsonl(full_dataset_dir / "all.jsonl")
    note_support = Counter(str(row.get("note_id") or "") for row in all_rows if str(row.get("note_id") or ""))
    ordered_note_ids = [note_id for note_id, _ in sorted(note_support.items(), key=lambda item: (-item[1], item[0]))]
    max_count = len(ordered_note_ids)

    checkpoints: list[int] = []
    current = int(args.start_note_count)
    while current < max_count:
        checkpoints.append(current)
        current += int(args.step)
    if max_count not in checkpoints:
        checkpoints.append(max_count)

    results: list[dict[str, Any]] = []
    for note_count in checkpoints:
        allowed_note_ids = set(ordered_note_ids[:note_count])
        subset_dir = working_dir / f"subset_{note_count:03d}"
        subset_stats = _build_subset(full_dir=full_dataset_dir, subset_dir=subset_dir, allowed_note_ids=allowed_note_ids)

        model_dir = working_dir / f"model_{note_count:03d}"
        summary = train_tabular_cefr_baseline(
            train_path=str(subset_dir / "train.jsonl"),
            dev_path=str(subset_dir / "dev.jsonl"),
            test_path=str(subset_dir / "test.jsonl"),
            output_dir=str(model_dir),
            model_names=["xgboost_gpu"],
            seed=args.seed,
            label_field="note_id",
            feature_profile=args.feature_profile,
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
        print(json.dumps(row, ensure_ascii=False))

    report = {
        "experiment": "note_id_cardinality_curve_contract_raw_v1",
        "input_path": str(Path(args.input_path).resolve()),
        "feature_profile": args.feature_profile,
        "start_note_count": args.start_note_count,
        "step": args.step,
        "full_dataset_stats": full_stats,
        "results": results,
    }
    (working_dir / "curve_results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (working_dir / "curve_results.csv").write_text(
        "unique_note_ids,train_samples,dev_samples,test_samples,dev_accuracy,dev_macro_f1,test_accuracy_argmax,test_macro_f1,test_top1,test_top3,test_top5\n"
        + "\n".join(
            ",".join(
                [
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
            for row in results
        )
        + "\n",
        encoding="utf-8",
    )
    _plot_curve(results, output_path=working_dir / "curve_metrics.png")


if __name__ == "__main__":
    main()
