"""One-button orchestrator for classifier pipeline stages."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import time
from typing import Any

from .build_kb import build_kb_artifacts
from .build_train_dataset import build_train_dev_from_enriched_kb
from .metadata import build_classifier_metadata_from_kb
from .run_quality_cycle import run_quality_cycle
from .train_deberta_classifier import train_deberta_classifier


def run_full_orchestrator(
    *,
    run_id: str,
    output_dir: str = "artifacts/classifier_orchestrator",
    kb_output_dir: str = "artifacts/classifier_kb",
    dataset_output_dir: str = "data/processed_classifier",
    model_output_dir: str = "artifacts/models/deberta_classifier_cefr",
    quality_output_dir: str = "artifacts/classifier_quality",
    spacy_model: str = "en_core_web_sm",
    dev_ratio: float = 0.2,
    seed: int = 42,
    model_name: str = "microsoft/deberta-v3-base",
    epochs: int = 3,
    batch_size: int = 8,
    learning_rate: float = 2e-5,
    max_length: int = 256,
    device: str = "cuda",
    max_attempts_per_gate: int = 3,
    required_consecutive_passes: int = 3,
) -> dict[str, Any]:
    if str(device).strip().lower() != "cuda":
        raise RuntimeError("GPU-only policy: orchestrator training supports only device='cuda'")
    try:
        import torch
    except Exception as exc:  # pragma: no cover
        raise ImportError("torch is required for orchestrator training") from exc
    if not torch.cuda.is_available():
        raise RuntimeError("GPU-only policy: CUDA is required for orchestrator training")

    started_at = time.time()
    stage_results: list[dict[str, Any]] = []
    artifacts: dict[str, Any] = {}
    status = "completed"
    failed_stage = None
    error_message = None

    def _run_stage(name: str, fn):
        stage_started = time.time()
        payload = fn()
        duration_ms = int((time.time() - stage_started) * 1000)
        stage_results.append(
            {
                "stage": name,
                "status": "completed",
                "duration_ms": duration_ms,
            }
        )
        return payload

    current_stage = "build_kb"
    try:
        current_stage = "build_kb"
        kb = _run_stage(
            "build_kb",
            lambda: build_kb_artifacts(output_dir=kb_output_dir, spacy_model=spacy_model),
        )
        artifacts["build_kb"] = kb

        current_stage = "build_train_dataset"
        ds = _run_stage(
            "build_train_dataset",
            lambda: build_train_dev_from_enriched_kb(
                input_path=kb["kb_spacy_enriched"],
                output_dir=dataset_output_dir,
                dev_ratio=dev_ratio,
                seed=seed,
            ),
        )
        artifacts["build_train_dataset"] = ds

        current_stage = "train_deberta"
        tr = _run_stage(
            "train_deberta",
            lambda: train_deberta_classifier(
                train_path=ds["train"],
                dev_path=ds["dev"],
                output_dir=model_output_dir,
                model_name=model_name,
                epochs=epochs,
                batch_size=batch_size,
                learning_rate=learning_rate,
                seed=seed,
                max_length=max_length,
                device=device,
            ),
        )
        artifacts["train_deberta"] = tr

        current_stage = "build_classifier_metadata"
        meta = _run_stage(
            "build_classifier_metadata",
            lambda: build_classifier_metadata_from_kb(
                kb_raw_path=kb["kb_raw"],
                output_dir=model_output_dir,
            ),
        )
        artifacts["build_classifier_metadata"] = meta

        current_stage = "run_quality_cycle"
        qc = _run_stage(
            "run_quality_cycle",
            lambda: run_quality_cycle(
                output_dir=quality_output_dir,
                run_id=run_id,
                max_attempts_per_gate=max_attempts_per_gate,
                required_consecutive_passes=required_consecutive_passes,
            ),
        )
        artifacts["run_quality_cycle"] = qc

    except Exception as exc:
        status = "failed"
        failed_stage = current_stage
        error_message = str(exc)
        stage_results.append(
            {
                "stage": failed_stage,
                "status": "failed",
                "duration_ms": 0,
                "error": error_message,
            }
        )

    total_duration_ms = int((time.time() - started_at) * 1000)
    summary = {
        "run_id": run_id,
        "status": status,
        "failed_stage": failed_stage,
        "error_message": error_message,
        "total_duration_ms": total_duration_ms,
        "stages": stage_results,
        "artifacts": artifacts,
        "config": {
            "kb_output_dir": kb_output_dir,
            "dataset_output_dir": dataset_output_dir,
            "model_output_dir": model_output_dir,
            "quality_output_dir": quality_output_dir,
            "spacy_model": spacy_model,
            "dev_ratio": dev_ratio,
            "seed": seed,
            "model_name": model_name,
            "epochs": epochs,
            "batch_size": batch_size,
            "learning_rate": learning_rate,
            "max_length": max_length,
            "device": device,
            "max_attempts_per_gate": max_attempts_per_gate,
            "required_consecutive_passes": required_consecutive_passes,
        },
    }

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = out_dir / "orchestrator_summary.json"
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    summary["summary_path"] = str(summary_path)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run full classifier orchestrator: build_kb -> build_train_dataset -> train_deberta -> run_quality_cycle."
    )
    parser.add_argument("--run-id", default="classifier-orchestrator-run")
    parser.add_argument("--output-dir", default="artifacts/classifier_orchestrator")
    parser.add_argument("--kb-output-dir", default="artifacts/classifier_kb")
    parser.add_argument("--dataset-output-dir", default="data/processed_classifier")
    parser.add_argument("--model-output-dir", default="artifacts/models/deberta_classifier_cefr")
    parser.add_argument("--quality-output-dir", default="artifacts/classifier_quality")
    parser.add_argument("--spacy-model", default="en_core_web_sm")
    parser.add_argument("--dev-ratio", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--model-name", default="microsoft/deberta-v3-base")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--learning-rate", type=float, default=2e-5)
    parser.add_argument("--max-length", type=int, default=256)
    parser.add_argument("--device", default="cuda", choices=["cuda"])
    parser.add_argument("--max-attempts-per-gate", type=int, default=3)
    parser.add_argument("--required-consecutive-passes", type=int, default=3)
    args = parser.parse_args()

    summary = run_full_orchestrator(
        run_id=args.run_id,
        output_dir=args.output_dir,
        kb_output_dir=args.kb_output_dir,
        dataset_output_dir=args.dataset_output_dir,
        model_output_dir=args.model_output_dir,
        quality_output_dir=args.quality_output_dir,
        spacy_model=args.spacy_model,
        dev_ratio=args.dev_ratio,
        seed=args.seed,
        model_name=args.model_name,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        max_length=args.max_length,
        device=args.device,
        max_attempts_per_gate=args.max_attempts_per_gate,
        required_consecutive_passes=args.required_consecutive_passes,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
