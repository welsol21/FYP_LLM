"""Run deterministic inference quality control over a fixed probe set."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List

from ela_pipeline.inference.run import run_pipeline


DEFAULT_PROBES = [
    "She should have trusted her instincts before making the decision.",
    "The team often works in the office.",
    "Although the weather was cold, they continued the study.",
    "This analysis is very important for the project.",
    "Managers analyze complex data in the city.",
]


def _walk_nodes(node: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    yield node
    for child in node.get("linguistic_elements", []) or []:
        if isinstance(child, dict):
            yield from _walk_nodes(child)


def _extract_probe_stats(result: Dict[str, Any]) -> Dict[str, int]:
    root = next(iter(result.values()))
    nodes = list(_walk_nodes(root))
    model_notes = 0
    fallback_notes = 0
    rejected_nodes = 0
    for node in nodes:
        quality_flags = node.get("quality_flags", []) or []
        if "model_used" in quality_flags or "note_generated" in quality_flags:
            model_notes += 1
        if "fallback_used" in quality_flags:
            fallback_notes += 1
        if node.get("rejected_candidates"):
            rejected_nodes += 1
    return {
        "nodes": len(nodes),
        "model_notes": model_notes,
        "fallback_notes": fallback_notes,
        "rejected_nodes": rejected_nodes,
    }


def _default_output_path() -> str:
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"docs/inference_quality_control_{ts}.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Inference quality control report")
    parser.add_argument(
        "--model-dir",
        required=True,
        help="Path to model directory for inference.",
    )
    parser.add_argument(
        "--probes-file",
        default=None,
        help="Optional JSON file with probe sentences list.",
    )
    parser.add_argument("--spacy-model", default="en_core_web_sm")
    parser.add_argument("--validation-mode", default="v2_strict", choices=["v1", "v2_strict"])
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    probes: List[str] = DEFAULT_PROBES
    if args.probes_file:
        loaded = json.loads(Path(args.probes_file).read_text(encoding="utf-8"))
        if not isinstance(loaded, list) or not all(isinstance(x, str) for x in loaded):
            raise SystemExit("probes_file must contain a JSON array of strings")
        probes = loaded

    report: Dict[str, Any] = {
        "model_dir": args.model_dir,
        "probe_count": len(probes),
        "probes": [],
        "aggregate": {
            "total_nodes": 0,
            "total_model_notes": 0,
            "total_fallback_notes": 0,
            "rejected_nodes_total": 0,
            # L1-L4 are reserved for template-selector coverage integration.
            "coverage_l1_exact": 0.0,
            "coverage_l2_drop_tam": 0.0,
            "coverage_l3_level_pos": 0.0,
            "coverage_l4_level_fallback": 0.0,
        },
    }

    for text in probes:
        result = run_pipeline(
            text=text,
            model_dir=args.model_dir,
            spacy_model=args.spacy_model,
            validation_mode=args.validation_mode,
        )
        stats = _extract_probe_stats(result)
        report["probes"].append({"text": text, **stats})
        report["aggregate"]["total_nodes"] += stats["nodes"]
        report["aggregate"]["total_model_notes"] += stats["model_notes"]
        report["aggregate"]["total_fallback_notes"] += stats["fallback_notes"]
        report["aggregate"]["rejected_nodes_total"] += stats["rejected_nodes"]

    total_nodes = report["aggregate"]["total_nodes"]
    report["aggregate"]["accepted_note_rate"] = (
        round(report["aggregate"]["total_model_notes"] / total_nodes, 6) if total_nodes else 0.0
    )
    report["aggregate"]["fallback_rate"] = (
        round(report["aggregate"]["total_fallback_notes"] / total_nodes, 6) if total_nodes else 0.0
    )

    out = args.output or _default_output_path()
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(out)
    print(json.dumps(report["aggregate"], indent=2))


if __name__ == "__main__":
    main()
