"""Run deterministic phonetic quality control over a fixed probe set."""

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
]


def _walk_nodes(node: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    yield node
    for child in node.get("linguistic_elements", []) or []:
        if isinstance(child, dict):
            yield from _walk_nodes(child)


def _extract_phonetic_probe_stats(result: Dict[str, Any]) -> Dict[str, Any]:
    root = next(iter(result.values()))
    nodes = list(_walk_nodes(root))
    non_sentence_nodes = [n for n in nodes if str(n.get("type") or "").strip() != "Sentence"]

    valid_node_phonetics = 0
    missing_phonetic_nodes = 0
    invalid_phonetic_nodes = 0

    def is_valid_phonetic(ph: Any) -> bool:
        return (
            isinstance(ph, dict)
            and isinstance(ph.get("uk"), str)
            and isinstance(ph.get("us"), str)
            and ph.get("uk", "").strip() != ""
            and ph.get("us", "").strip() != ""
        )

    for node in non_sentence_nodes:
        ph = node.get("phonetic")
        if ph is None:
            missing_phonetic_nodes += 1
            continue
        if is_valid_phonetic(ph):
            valid_node_phonetics += 1
        else:
            invalid_phonetic_nodes += 1

    sentence_phonetic_ok = is_valid_phonetic(root.get("phonetic"))
    total_non_sentence = len(non_sentence_nodes)
    node_phonetic_coverage = round(valid_node_phonetics / total_non_sentence, 6) if total_non_sentence else 0.0

    return {
        "nodes": len(nodes),
        "non_sentence_nodes": total_non_sentence,
        "valid_node_phonetics": valid_node_phonetics,
        "missing_phonetic_nodes": missing_phonetic_nodes,
        "invalid_phonetic_nodes": invalid_phonetic_nodes,
        "sentence_phonetic_ok": sentence_phonetic_ok,
        "node_phonetic_coverage": node_phonetic_coverage,
    }


def _default_output_path() -> str:
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"docs/reports/phonetic_qc_{ts}.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Phonetic quality control report")
    parser.add_argument("--spacy-model", default="en_core_web_sm")
    parser.add_argument("--validation-mode", default="v2_strict", choices=["v1", "v2_strict"])
    parser.add_argument("--phonetic-provider", default="espeak", choices=["espeak"])
    parser.add_argument("--phonetic-binary", default="auto", choices=["auto", "espeak", "espeak-ng"])
    parser.add_argument("--phonetic-nodes", action="store_true", help="Evaluate phrase/word phonetic coverage too.")
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
        "phonetic_provider": args.phonetic_provider,
        "probe_count": len(probes),
        "probes": [],
        "aggregate": {
            "total_nodes": 0,
            "total_non_sentence_nodes": 0,
            "valid_node_phonetics": 0,
            "missing_phonetic_nodes": 0,
            "invalid_phonetic_nodes": 0,
            "sentence_phonetic_ok_count": 0,
        },
    }

    for text in probes:
        result = run_pipeline(
            text=text,
            model_dir=None,
            spacy_model=args.spacy_model,
            validation_mode=args.validation_mode,
            enable_phonetic=True,
            phonetic_provider=args.phonetic_provider,
            phonetic_binary=args.phonetic_binary,
            phonetic_nodes=bool(args.phonetic_nodes),
        )
        stats = _extract_phonetic_probe_stats(result)
        report["probes"].append({"text": text, **stats})

        report["aggregate"]["total_nodes"] += stats["nodes"]
        report["aggregate"]["total_non_sentence_nodes"] += stats["non_sentence_nodes"]
        report["aggregate"]["valid_node_phonetics"] += stats["valid_node_phonetics"]
        report["aggregate"]["missing_phonetic_nodes"] += stats["missing_phonetic_nodes"]
        report["aggregate"]["invalid_phonetic_nodes"] += stats["invalid_phonetic_nodes"]
        report["aggregate"]["sentence_phonetic_ok_count"] += 1 if stats["sentence_phonetic_ok"] else 0

    total_non_sentence = report["aggregate"]["total_non_sentence_nodes"]
    probe_count = report["probe_count"]
    report["aggregate"]["node_phonetic_coverage"] = (
        round(report["aggregate"]["valid_node_phonetics"] / total_non_sentence, 6) if total_non_sentence else 0.0
    )
    report["aggregate"]["sentence_phonetic_ok_rate"] = (
        round(report["aggregate"]["sentence_phonetic_ok_count"] / probe_count, 6) if probe_count else 0.0
    )

    out = args.output or _default_output_path()
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(out)
    print(json.dumps(report["aggregate"], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
