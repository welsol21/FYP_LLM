"""Run deterministic CEFR quality control over a fixed probe set."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List

from ela_pipeline.inference.run import CEFR_LEVEL_TO_INDEX, CEFR_LEVEL_ORDER, run_pipeline


DEFAULT_PROBES = [
    "She should have trusted her instincts before making the decision.",
    "The team often works in the office.",
    "Although the weather was cold, they continued the study.",
]

FUNCTION_WORD_POS = {
    "article",
    "auxiliary verb",
    "determiner",
    "pronoun",
    "preposition",
    "conjunction",
    "particle",
}


def _walk_nodes(node: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    yield node
    for child in node.get("linguistic_elements", []) or []:
        if isinstance(child, dict):
            yield from _walk_nodes(child)


def _extract_cefr_probe_stats(result: Dict[str, Any]) -> Dict[str, Any]:
    root = next(iter(result.values()))
    sentence_level = str(root.get("cefr_level") or "").strip().upper()
    nodes = list(_walk_nodes(root))

    valid_levels = 0
    invalid_levels = 0
    function_word_over_b1 = 0
    over_sentence_plus_2 = 0
    over_parent_plus_1 = 0

    dist = {label: 0 for label in CEFR_LEVEL_ORDER}

    def recurse(node: Dict[str, Any], parent_level: str | None) -> None:
        nonlocal valid_levels, invalid_levels, function_word_over_b1, over_sentence_plus_2, over_parent_plus_1

        level = str(node.get("cefr_level") or "").strip().upper()
        node_type = str(node.get("type") or "").strip()
        pos = str(node.get("part_of_speech") or "").strip().lower()

        if level in CEFR_LEVEL_TO_INDEX:
            valid_levels += 1
            dist[level] += 1
            if node_type == "Word" and pos in FUNCTION_WORD_POS and CEFR_LEVEL_TO_INDEX[level] > CEFR_LEVEL_TO_INDEX["B1"]:
                function_word_over_b1 += 1
            if sentence_level in CEFR_LEVEL_TO_INDEX and node_type != "Sentence":
                if CEFR_LEVEL_TO_INDEX[level] > CEFR_LEVEL_TO_INDEX[sentence_level] + 2:
                    over_sentence_plus_2 += 1
            if parent_level in CEFR_LEVEL_TO_INDEX and CEFR_LEVEL_TO_INDEX[level] > CEFR_LEVEL_TO_INDEX[parent_level] + 1:
                over_parent_plus_1 += 1
        else:
            invalid_levels += 1

        for child in node.get("linguistic_elements", []) or []:
            if isinstance(child, dict):
                recurse(child, level if level in CEFR_LEVEL_TO_INDEX else parent_level)

    recurse(root, None)

    total_nodes = len(nodes)
    valid_ratio = round(valid_levels / total_nodes, 6) if total_nodes else 0.0
    non_sentence_nodes = len([n for n in nodes if str(n.get("type") or "").strip() != "Sentence"])
    anomaly_total = function_word_over_b1 + over_sentence_plus_2 + over_parent_plus_1
    anomaly_rate = round(anomaly_total / non_sentence_nodes, 6) if non_sentence_nodes else 0.0

    return {
        "nodes": total_nodes,
        "valid_levels": valid_levels,
        "invalid_levels": invalid_levels,
        "valid_ratio": valid_ratio,
        "function_word_over_b1": function_word_over_b1,
        "over_sentence_plus_2": over_sentence_plus_2,
        "over_parent_plus_1": over_parent_plus_1,
        "anomaly_rate": anomaly_rate,
        "distribution": dist,
    }


def _default_output_path() -> str:
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"docs/reports/cefr_qc_{ts}.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="CEFR quality control report")
    parser.add_argument("--spacy-model", default="en_core_web_sm")
    parser.add_argument("--validation-mode", default="v2_strict", choices=["v1", "v2_strict"])
    parser.add_argument("--cefr-provider", default="t5", choices=["rule", "t5"])
    parser.add_argument("--cefr-model-path", default="artifacts/models/t5_cefr/best_model")
    parser.add_argument("--cefr-nodes", action="store_true", help="Evaluate phrase/word CEFR coverage too.")
    parser.add_argument("--probes-file", default=None, help="Optional JSON file with probe sentence list.")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    probes: List[str] = DEFAULT_PROBES
    if args.probes_file:
        loaded = json.loads(Path(args.probes_file).read_text(encoding="utf-8"))
        if not isinstance(loaded, list) or not all(isinstance(x, str) for x in loaded):
            raise SystemExit("probes_file must contain a JSON array of strings")
        probes = loaded

    report: Dict[str, Any] = {
        "cefr_provider": args.cefr_provider,
        "cefr_model_path": args.cefr_model_path,
        "probe_count": len(probes),
        "probes": [],
        "aggregate": {
            "total_nodes": 0,
            "valid_levels": 0,
            "invalid_levels": 0,
            "function_word_over_b1": 0,
            "over_sentence_plus_2": 0,
            "over_parent_plus_1": 0,
            "distribution": {label: 0 for label in CEFR_LEVEL_ORDER},
        },
    }

    for text in probes:
        result = run_pipeline(
            text=text,
            model_dir=None,
            spacy_model=args.spacy_model,
            validation_mode=args.validation_mode,
            enable_cefr=True,
            cefr_provider=args.cefr_provider,
            cefr_model_path=args.cefr_model_path,
            cefr_nodes=bool(args.cefr_nodes),
        )
        stats = _extract_cefr_probe_stats(result)
        report["probes"].append({"text": text, **stats})

        report["aggregate"]["total_nodes"] += stats["nodes"]
        report["aggregate"]["valid_levels"] += stats["valid_levels"]
        report["aggregate"]["invalid_levels"] += stats["invalid_levels"]
        report["aggregate"]["function_word_over_b1"] += stats["function_word_over_b1"]
        report["aggregate"]["over_sentence_plus_2"] += stats["over_sentence_plus_2"]
        report["aggregate"]["over_parent_plus_1"] += stats["over_parent_plus_1"]
        for label in CEFR_LEVEL_ORDER:
            report["aggregate"]["distribution"][label] += stats["distribution"][label]

    total_nodes = report["aggregate"]["total_nodes"]
    anomaly_total = (
        report["aggregate"]["function_word_over_b1"]
        + report["aggregate"]["over_sentence_plus_2"]
        + report["aggregate"]["over_parent_plus_1"]
    )
    report["aggregate"]["valid_ratio"] = round(report["aggregate"]["valid_levels"] / total_nodes, 6) if total_nodes else 0.0
    report["aggregate"]["anomaly_rate"] = round(anomaly_total / total_nodes, 6) if total_nodes else 0.0

    out = args.output or _default_output_path()
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(out)
    print(json.dumps(report["aggregate"], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
