"""Build sentence candidates from OANC zip packages."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any
from collections import Counter, defaultdict
from functools import lru_cache
import re
import xml.etree.ElementTree as ET
import zipfile

import spacy

from .oanc_inspect import extract_oanc_text, list_oanc_candidate_files


_WHITESPACE_RE = re.compile(r"\s+")
_PARAGRAPH_SPLIT_RE = re.compile(r"\n+")
_OANC_SENTENCE_SPLITTER = "spacy_parser"
_OANC_SENTENCE_SPLITTER_MODEL = "en_core_web_sm"


def _normalize_sentence(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", str(text or "")).strip()


def _genre_bucket(member_path: str) -> str:
    parts = PurePosixPath(member_path).parts
    try:
        data_index = parts.index("data")
    except ValueError:
        return "unknown"
    if len(parts) <= data_index + 2:
        return "unknown"
    return "/".join(parts[data_index + 1 : data_index + 3])


def _sentence_annotation_path(member_path: str) -> str:
    path = PurePosixPath(member_path)
    return str(path.with_name(f"{path.stem}-s.xml"))


@lru_cache(maxsize=1)
def _load_sentence_nlp():
    return spacy.load(_OANC_SENTENCE_SPLITTER_MODEL, disable=["ner"])


def split_oanc_text_to_sentences(text: str, *, min_chars: int = 20, max_chars: int = 400) -> list[str]:
    pieces: list[str] = []
    paragraphs = [segment.strip() for segment in _PARAGRAPH_SPLIT_RE.split(str(text or "")) if segment.strip()]
    if not paragraphs:
        return []

    for paragraph in paragraphs:
        normalized = _normalize_sentence(paragraph)
        if not normalized:
            continue
        if not re.search(r"[.!?]$", normalized) and len(normalized) <= 80:
            continue

        doc = _load_sentence_nlp()(normalized)
        for sent in doc.sents:
            candidate = _normalize_sentence(sent.text)
            if candidate:
                pieces.append(candidate)

    out: list[str] = []
    for piece in pieces:
        sentence = _normalize_sentence(piece)
        if len(sentence) < min_chars or len(sentence) > max_chars:
            continue
        out.append(sentence)
    return out


def extract_oanc_annotated_sentences(
    zip_path: str,
    member_path: str,
    *,
    min_chars: int = 20,
    max_chars: int = 400,
) -> list[dict[str, str]]:
    text = extract_oanc_text(zip_path, member_path)
    annotation_path = _sentence_annotation_path(member_path)
    rows: list[dict[str, str]] = []
    with zipfile.ZipFile(zip_path) as zf:
        try:
            xml_payload = zf.read(annotation_path).decode("utf-8", errors="replace")
        except KeyError:
            return rows

    root = ET.fromstring(xml_payload)
    ns = {"x": "http://www.xces.org/schema/2003"}
    for struct in root.findall(".//x:struct[@type='s']", ns):
        start = int(struct.attrib.get("from", "0"))
        end = int(struct.attrib.get("to", "0"))
        annotation_id = ""
        feat = struct.find("./x:feat[@name='id']", ns)
        if feat is not None:
            annotation_id = str(feat.attrib.get("value", "")).strip()
        sentence = _normalize_sentence(text[start:end])
        if len(sentence) < min_chars or len(sentence) > max_chars:
            continue
        rows.append({"text": sentence, "annotation_id": annotation_id})
    return rows


def build_oanc_sentence_candidates(
    zip_path: str,
    *,
    member_paths: list[str] | None = None,
    limit_files: int | None = None,
    min_chars: int = 20,
    max_chars: int = 400,
) -> list[dict[str, Any]]:
    if member_paths is None:
        member_paths = list_oanc_candidate_files(zip_path)
        if limit_files is not None:
            member_paths = member_paths[: max(0, int(limit_files))]

    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for member_path in member_paths:
        annotated_rows = extract_oanc_annotated_sentences(
            zip_path,
            member_path,
            min_chars=min_chars,
            max_chars=max_chars,
        )
        sentence_rows: list[dict[str, Any]] = []
        if annotated_rows:
            for idx, annotated in enumerate(annotated_rows):
                sentence_rows.append(
                    {
                        "text": annotated["text"],
                        "sentence_index_in_file": idx,
                        "sentence_boundary_source": "oanc_s_xml",
                        "sentence_annotation_id": annotated.get("annotation_id", ""),
                    }
                )
        else:
            raw_text = extract_oanc_text(zip_path, member_path)
            for idx, sentence in enumerate(
                split_oanc_text_to_sentences(raw_text, min_chars=min_chars, max_chars=max_chars)
            ):
                sentence_rows.append(
                    {
                        "text": sentence,
                        "sentence_index_in_file": idx,
                        "sentence_boundary_source": "spacy_parser",
                        "sentence_annotation_id": "",
                    }
                )
        bucket = _genre_bucket(member_path)
        for sentence_row in sentence_rows:
            sentence = str(sentence_row["text"])
            dedup_key = (bucket, sentence.lower())
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            rows.append(
                {
                    "text": sentence,
                    "provenance": {
                        "source": "OANC",
                        "member_path": member_path,
                        "genre_bucket": bucket,
                        "sentence_index_in_file": int(sentence_row["sentence_index_in_file"]),
                        "sentence_boundary_source": sentence_row["sentence_boundary_source"],
                        "sentence_annotation_id": sentence_row["sentence_annotation_id"],
                        "sentence_splitter_model": _OANC_SENTENCE_SPLITTER_MODEL,
                    },
                }
            )
    return rows


def build_oanc_candidate_manifest(
    zip_path: str,
    *,
    per_bucket_limit: int | None = None,
    total_limit: int | None = None,
) -> dict[str, Any]:
    member_paths = list_oanc_candidate_files(zip_path)
    selected: list[str] = []
    bucket_counts: Counter[str] = Counter()
    grouped: dict[str, list[str]] = defaultdict(list)
    for member_path in member_paths:
        grouped[_genre_bucket(member_path)].append(member_path)

    for bucket in sorted(grouped):
        items = grouped[bucket]
        if per_bucket_limit is not None:
            items = items[: max(0, int(per_bucket_limit))]
        for item in items:
            if total_limit is not None and len(selected) >= int(total_limit):
                break
            selected.append(item)
            bucket_counts[bucket] += 1
        if total_limit is not None and len(selected) >= int(total_limit):
            break

    return {
        "zip_path": zip_path,
        "selected_files": len(selected),
        "bucket_counts": dict(bucket_counts),
        "member_paths": selected,
    }
