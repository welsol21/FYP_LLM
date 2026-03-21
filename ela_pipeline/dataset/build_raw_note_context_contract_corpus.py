"""Build raw contract corpus from note/context pairs without template-family filtering."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

from ela_pipeline.annotate.contract_template_builder import build_contract_template_payload
from ela_pipeline.dataset.build_book_explanation_context_corpus import _walk_with_parent
from ela_pipeline.parse.spacy_parser import load_nlp
from ela_pipeline.skeleton.builder import build_skeleton


def _iter_jsonl(path: str):
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def _write_json(path: str, payload: dict[str, Any]) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: str, rows: list[dict[str, Any]]) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def build_raw_note_context_contract_rows(
    note_context_rows: list[dict[str, Any]],
    *,
    spacy_model: str = "en_core_web_sm",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    nlp = load_nlp(spacy_model)
    out_rows: list[dict[str, Any]] = []
    stats = {
        "pair_rows": len(note_context_rows),
        "contracts_built": 0,
        "contracts_failed": 0,
    }

    for idx, row in enumerate(note_context_rows):
        context_text = str(row.get("context_text") or "").strip()
        if not context_text:
            continue
        try:
            contract_doc = build_skeleton(context_text, nlp)
        except Exception:
            stats["contracts_failed"] += 1
            continue
        if not contract_doc:
            stats["contracts_failed"] += 1
            continue

        contract_doc = copy.deepcopy(contract_doc)
        for sentence_text, sentence_node in contract_doc.items():
            sentence_children = [child for child in (sentence_node.get("linguistic_elements") or []) if isinstance(child, dict)]
            sentence_payload = build_contract_template_payload(
                node=sentence_node,
                sentence_node=sentence_node,
                parent=None,
                path_types=["Sentence"],
                depth=0,
                sibling_index=0,
                sibling_count=1,
            )
            if sentence_payload is not None:
                sentence_node["contract_template_payload"] = sentence_payload
            for child_index, child in enumerate(sentence_children):
                for node, parent, path_types, node_sibling_index, node_sibling_count in _walk_with_parent(
                    child,
                    parent=sentence_node,
                    path_types=["Sentence"],
                    sibling_index=child_index,
                    sibling_count=max(1, len(sentence_children)),
                ):
                    if str(node.get("type") or "") not in {"Phrase", "Sentence"}:
                        continue
                    payload = build_contract_template_payload(
                        node=node,
                        sentence_node=sentence_node,
                        parent=parent,
                        path_types=path_types,
                        depth=max(0, len(path_types) - 1),
                        sibling_index=node_sibling_index,
                        sibling_count=node_sibling_count,
                    )
                    if payload is not None:
                        node["contract_template_payload"] = payload

        out_rows.append(
            {
                "row_id": row.get("row_id") or f"raw_note_context_{idx+1}",
                "source_path": row.get("source_path"),
                "heading": row.get("heading"),
                "topic_key": row.get("topic_key"),
                "notation_text": row.get("notation_text"),
                "context_text": row.get("context_text"),
                "pair_method": row.get("pair_method"),
                "example_label": row.get("example_label"),
                "confidence": row.get("confidence"),
                "page_num": row.get("page_num"),
                "raw_ocr_line": row.get("raw_ocr_line"),
                "context_contract": contract_doc,
            }
        )
        stats["contracts_built"] += 1

    report = {
        "pipeline_version": "raw_note_context_contract_corpus_v1",
        "spacy_model": spacy_model,
        "stats": stats,
    }
    return out_rows, report


def main() -> None:
    parser = argparse.ArgumentParser(description="Build raw contract corpus from note/context pairs.")
    parser.add_argument("--input-jsonl", required=True)
    parser.add_argument("--output-jsonl", required=True)
    parser.add_argument("--report-json", required=True)
    parser.add_argument("--spacy-model", default="en_core_web_sm")
    args = parser.parse_args()

    rows, report = build_raw_note_context_contract_rows(
        list(_iter_jsonl(args.input_jsonl)),
        spacy_model=args.spacy_model,
    )
    _write_jsonl(args.output_jsonl, rows)
    _write_json(args.report_json, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
