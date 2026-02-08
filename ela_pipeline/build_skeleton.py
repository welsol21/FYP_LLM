"""CLI: build contract skeleton from input texts."""

from __future__ import annotations

import argparse
import json

from ela_pipeline.parse.spacy_parser import load_nlp
from ela_pipeline.skeleton.builder import build_skeleton
from ela_pipeline.validation.validator import raise_if_invalid, validate_contract


def main() -> None:
    parser = argparse.ArgumentParser(description="Build contract skeleton from text")
    parser.add_argument("--input", required=True, help="Input JSONL with field 'text'")
    parser.add_argument("--output", required=True)
    parser.add_argument("--spacy-model", default="en_core_web_sm")
    args = parser.parse_args()

    nlp = load_nlp(args.spacy_model)

    rows = []
    with open(args.input, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))

    docs = []
    for row in rows:
        contract_doc = build_skeleton(row["text"], nlp)
        raise_if_invalid(validate_contract(contract_doc))
        docs.append(contract_doc)

    with open(args.output, "w", encoding="utf-8") as f:
        for doc in docs:
            f.write(json.dumps(doc, ensure_ascii=False) + "\n")

    print(f"Saved {len(docs)} documents to {args.output}")


if __name__ == "__main__":
    main()
