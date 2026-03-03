"""CLI to build classifier metadata from KB or classifier dataset JSONL."""

from __future__ import annotations

import argparse
import json

from .metadata import build_classifier_metadata_from_dataset, build_classifier_metadata_from_kb


def main() -> None:
    parser = argparse.ArgumentParser(description="Build classifier_metadata.json for runtime DeBERTa classifier.")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--kb-raw-path", default="")
    parser.add_argument("--classifier-jsonl-path", default="")
    args = parser.parse_args()

    kb_raw = str(args.kb_raw_path or "").strip()
    ds = str(args.classifier_jsonl_path or "").strip()
    if bool(kb_raw) == bool(ds):
        raise ValueError("Provide exactly one source: --kb-raw-path OR --classifier-jsonl-path")

    if kb_raw:
        summary = build_classifier_metadata_from_kb(kb_raw_path=kb_raw, output_dir=args.output_dir)
    else:
        summary = build_classifier_metadata_from_dataset(classifier_jsonl_path=ds, output_dir=args.output_dir)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
