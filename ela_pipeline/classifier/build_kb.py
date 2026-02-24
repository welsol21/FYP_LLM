"""Build grammar KB artifacts (raw + spaCy-enriched)."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path

from ela_pipeline.parse.spacy_parser import load_nlp

from .kb import build_seed_grammar_kb
from .kb_enrichment import enrich_kb_example


def build_kb_artifacts(*, output_dir: str, spacy_model: str = "en_core_web_sm") -> dict[str, str]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_path = out_dir / "kb_raw.jsonl"
    enriched_path = out_dir / "kb_spacy_enriched.jsonl"

    rows = build_seed_grammar_kb()
    nlp = load_nlp(spacy_model)

    with raw_path.open("w", encoding="utf-8") as raw_f, enriched_path.open("w", encoding="utf-8") as enr_f:
        for row in rows:
            payload = asdict(row)
            raw_f.write(json.dumps(payload, ensure_ascii=False) + "\n")
            enriched = enrich_kb_example(payload["blueprint_intermediate"], nlp=nlp)
            enr_payload = {
                **payload,
                "spacy": enriched,
            }
            enr_f.write(json.dumps(enr_payload, ensure_ascii=False) + "\n")

    return {
        "kb_raw": str(raw_path),
        "kb_spacy_enriched": str(enriched_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build classifier grammar KB artifacts (raw + spaCy-enriched).")
    parser.add_argument("--output-dir", default="artifacts/classifier_kb")
    parser.add_argument("--spacy-model", default="en_core_web_sm")
    args = parser.parse_args()

    artifacts = build_kb_artifacts(output_dir=args.output_dir, spacy_model=args.spacy_model)
    print(json.dumps(artifacts, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
