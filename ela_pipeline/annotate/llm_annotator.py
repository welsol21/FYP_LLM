"""Dataset annotation entrypoint with strict frozen validation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ela_pipeline.annotate.local_generator import LocalT5Annotator
from ela_pipeline.contract import deep_copy_contract
from ela_pipeline.validation.validator import raise_if_invalid, validate_contract, validate_frozen_structure


def annotate_file(input_path: str, output_path: str, model_dir: str) -> None:
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    raise_if_invalid(validate_contract(data))
    skeleton = deep_copy_contract(data)

    annotator = LocalT5Annotator(model_dir=model_dir)
    enriched = annotator.annotate(data)

    raise_if_invalid(validate_contract(enriched))
    raise_if_invalid(validate_frozen_structure(skeleton, enriched))

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(enriched, f, ensure_ascii=False, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description="Annotate contract JSON with local LLM notes")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--model-dir", required=True)
    args = parser.parse_args()

    annotate_file(args.input, args.output, args.model_dir)
    print(f"Saved: {args.output}")


if __name__ == "__main__":
    main()
