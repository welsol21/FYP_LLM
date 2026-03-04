"""PMC Open Access ingest helpers for bounded advanced-register harvesting."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import spacy


def _clean_text(value: str) -> str:
    return " ".join(str(value or "").split())


def _collect_text(element: ET.Element) -> str:
    return _clean_text("".join(element.itertext()))


@lru_cache(maxsize=1)
def _load_sentencizer():
    nlp = spacy.blank("en")
    nlp.add_pipe("sentencizer")
    return nlp


def extract_pmc_article(xml_path: str) -> dict[str, Any]:
    src = Path(xml_path)
    if not src.is_file():
        raise FileNotFoundError(f"PMC XML file not found: {xml_path}")

    root = ET.fromstring(src.read_text(encoding="utf-8"))

    article_id = ""
    for node in root.findall(".//article-id"):
        if node.get("pub-id-type") in {"pmcid", "pmc", "publisher-id"}:
            article_id = _clean_text(node.text or "")
            if article_id:
                break

    title = _clean_text(" ".join(_collect_text(node) for node in root.findall(".//title-group/article-title")))
    abstract_parts = [_collect_text(node) for node in root.findall(".//abstract//p")]
    body_parts = [_collect_text(node) for node in root.findall(".//body//p")]
    license_parts = [_collect_text(node) for node in root.findall(".//permissions//license-p")]
    journal_title = _clean_text(" ".join(_collect_text(node) for node in root.findall(".//journal-title")))

    return {
        "article_id": article_id,
        "title": title,
        "journal_title": journal_title,
        "license_text": _clean_text(" ".join(part for part in license_parts if part)),
        "abstract_paragraphs": [part for part in abstract_parts if part],
        "body_paragraphs": [part for part in body_parts if part],
        "source_path": str(src),
    }


def build_pmc_sentence_candidates(article: dict[str, Any]) -> list[dict[str, Any]]:
    article_id = str(article.get("article_id") or "").strip()
    journal_title = str(article.get("journal_title") or "").strip()
    license_text = str(article.get("license_text") or "").strip()
    title = str(article.get("title") or "").strip()

    paragraphs = []
    for section_name in ("abstract_paragraphs", "body_paragraphs"):
        for paragraph in article.get(section_name, []):
            text = _clean_text(str(paragraph or ""))
            if len(text) < 40:
                continue
            paragraphs.append((section_name, text))

    rows: list[dict[str, Any]] = []
    nlp = _load_sentencizer()
    for idx, (section_name, text) in enumerate(paragraphs, start=1):
        doc = nlp(text)
        sentence_index = 0
        for sent in doc.sents:
            sentence_text = _clean_text(sent.text)
            if len(sentence_text) < 20:
                continue
            sentence_index += 1
            rows.append(
                {
                    "text": sentence_text,
                    "provenance": {
                        "source": "PMC_OA",
                        "article_id": article_id,
                        "journal_title": journal_title,
                        "license_text": license_text,
                        "title": title,
                        "section": section_name,
                        "paragraph_index": idx,
                        "sentence_index": sentence_index,
                        "source_path": str(article.get("source_path") or ""),
                    },
                }
            )
    return rows
