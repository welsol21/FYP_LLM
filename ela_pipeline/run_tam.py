"""CLI: apply TAM labels to contract JSONL."""

from __future__ import annotations

import argparse
import json

from ela_pipeline.parse.spacy_parser import load_nlp
from ela_pipeline.tam.rules import apply_tam
from ela_pipeline.validation.validator import raise_if_invalid, validate_contract


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply TAM rules to contract JSONL")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--spacy-model", default="en_core_web_sm")
    args = parser.parse_args()

    nlp = load_nlp(args.spacy_model)

    outputs = []
    with open(args.input, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            doc = json.loads(line)
            apply_tam(doc, nlp)
            raise_if_invalid(validate_contract(doc))
            outputs.append(doc)

    with open(args.output, "w", encoding="utf-8") as f:
        for doc in outputs:
            f.write(json.dumps(doc, ensure_ascii=False) + "\n")

    print(f"Saved {len(outputs)} TAM-annotated documents to {args.output}")


if __name__ == "__main__":
    main()
