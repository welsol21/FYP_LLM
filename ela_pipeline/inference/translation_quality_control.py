"""Run deterministic translation quality control over a fixed probe set."""

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


def _extract_translation_probe_stats(
    result: Dict[str, Any],
    *,
    source_lang: str,
    target_lang: str,
) -> Dict[str, Any]:
    root = next(iter(result.values()))
    nodes = list(_walk_nodes(root))

    translated_nodes = 0
    empty_translation_nodes = 0
    missing_translation_nodes = 0
    lang_mismatch_nodes = 0

    # Node coverage excludes sentence node because sentence translation is tracked separately.
    non_sentence_nodes = [n for n in nodes if str(n.get("type") or "").strip() != "Sentence"]
    for node in non_sentence_nodes:
        tr = node.get("translation")
        if not isinstance(tr, dict):
            missing_translation_nodes += 1
            continue
        text = tr.get("text")
        if not isinstance(text, str) or text.strip() == "":
            empty_translation_nodes += 1
            continue
        translated_nodes += 1
        if tr.get("source_lang") != source_lang or tr.get("target_lang") != target_lang:
            lang_mismatch_nodes += 1

    sentence_tr = root.get("translation")
    sentence_translation_ok = (
        isinstance(sentence_tr, dict)
        and isinstance(sentence_tr.get("text"), str)
        and sentence_tr.get("text", "").strip() != ""
        and sentence_tr.get("source_lang") == source_lang
        and sentence_tr.get("target_lang") == target_lang
    )

    total_non_sentence = len(non_sentence_nodes)
    node_translation_coverage = round(translated_nodes / total_non_sentence, 6) if total_non_sentence else 0.0

    return {
        "nodes": len(nodes),
        "non_sentence_nodes": total_non_sentence,
        "translated_nodes": translated_nodes,
        "missing_translation_nodes": missing_translation_nodes,
        "empty_translation_nodes": empty_translation_nodes,
        "lang_mismatch_nodes": lang_mismatch_nodes,
        "sentence_translation_ok": sentence_translation_ok,
        "node_translation_coverage": node_translation_coverage,
    }


def _default_output_path() -> str:
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"docs/reports/translation_qc_{ts}.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Translation quality control report")
    parser.add_argument("--spacy-model", default="en_core_web_sm")
    parser.add_argument("--validation-mode", default="v2_strict", choices=["v1", "v2_strict"])
    parser.add_argument("--source-lang", default="en")
    parser.add_argument("--target-lang", default="ru")
    parser.add_argument("--translation-provider", default="m2m100", choices=["m2m100"])
    parser.add_argument("--translation-model", default="facebook/m2m100_418M")
    parser.add_argument("--translation-device", default="auto", choices=["auto", "cpu", "cuda"])
    parser.add_argument("--translate-nodes", action="store_true", help="Evaluate phrase/word translation coverage too.")
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
        "translation_provider": args.translation_provider,
        "translation_model": args.translation_model,
        "source_lang": args.source_lang,
        "target_lang": args.target_lang,
        "probe_count": len(probes),
        "probes": [],
        "aggregate": {
            "total_nodes": 0,
            "total_non_sentence_nodes": 0,
            "translated_nodes": 0,
            "missing_translation_nodes": 0,
            "empty_translation_nodes": 0,
            "lang_mismatch_nodes": 0,
            "sentence_translation_ok_count": 0,
        },
    }

    for text in probes:
        result = run_pipeline(
            text=text,
            model_dir=None,
            spacy_model=args.spacy_model,
            validation_mode=args.validation_mode,
            enable_translation=True,
            translation_provider=args.translation_provider,
            translation_model=args.translation_model,
            translation_source_lang=args.source_lang,
            translation_target_lang=args.target_lang,
            translation_device=args.translation_device,
            translate_nodes=bool(args.translate_nodes),
        )
        stats = _extract_translation_probe_stats(
            result,
            source_lang=args.source_lang,
            target_lang=args.target_lang,
        )
        report["probes"].append({"text": text, **stats})

        report["aggregate"]["total_nodes"] += stats["nodes"]
        report["aggregate"]["total_non_sentence_nodes"] += stats["non_sentence_nodes"]
        report["aggregate"]["translated_nodes"] += stats["translated_nodes"]
        report["aggregate"]["missing_translation_nodes"] += stats["missing_translation_nodes"]
        report["aggregate"]["empty_translation_nodes"] += stats["empty_translation_nodes"]
        report["aggregate"]["lang_mismatch_nodes"] += stats["lang_mismatch_nodes"]
        report["aggregate"]["sentence_translation_ok_count"] += 1 if stats["sentence_translation_ok"] else 0

    total_non_sentence = report["aggregate"]["total_non_sentence_nodes"]
    probe_count = report["probe_count"]

    report["aggregate"]["node_translation_coverage"] = (
        round(report["aggregate"]["translated_nodes"] / total_non_sentence, 6) if total_non_sentence else 0.0
    )
    report["aggregate"]["sentence_translation_ok_rate"] = (
        round(report["aggregate"]["sentence_translation_ok_count"] / probe_count, 6) if probe_count else 0.0
    )
    report["aggregate"]["translation_issue_rate"] = (
        round(
            (
                report["aggregate"]["missing_translation_nodes"]
                + report["aggregate"]["empty_translation_nodes"]
                + report["aggregate"]["lang_mismatch_nodes"]
            )
            / total_non_sentence,
            6,
        )
        if total_non_sentence
        else 0.0
    )

    out = args.output or _default_output_path()
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(out)
    print(json.dumps(report["aggregate"], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
