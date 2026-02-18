"""Media extraction + contract build pipeline for runtime HTTP flow."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any

from ela_pipeline.client_storage import build_sentence_hash
from ela_pipeline.parse.spacy_parser import load_nlp
from ela_pipeline.skeleton.builder import build_skeleton
from ela_pipeline.tam.rules import apply_tam


@dataclass(frozen=True)
class MediaPipelineResult:
    source_type: str
    full_text: str
    text_hash: str
    media_sentences: list[dict[str, Any]]
    contract_sentences: list[dict[str, Any]]


def _detect_source_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md", ".rtf"}:
        return "text"
    if suffix in {".pdf"}:
        return "pdf"
    if suffix in {".mp3", ".wav", ".m4a", ".flac", ".ogg"}:
        return "audio"
    if suffix in {".mp4", ".mkv", ".mov", ".avi", ".webm"}:
        return "video"
    return "text"


def _extract_text(source_path: Path, source_type: str) -> str:
    if source_type == "text":
        return source_path.read_text(encoding="utf-8", errors="ignore").strip()

    if source_type == "pdf":
        try:
            from pypdf import PdfReader
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("PDF extraction requires `pypdf` dependency.") from exc
        reader = PdfReader(str(source_path))
        chunks: list[str] = []
        for page in reader.pages:
            page_text = (page.extract_text() or "").strip()
            if page_text:
                chunks.append(page_text)
        return "\n".join(chunks).strip()

    if source_type in {"audio", "video"}:
        # Current pragmatic path before ASR integration:
        # use sidecar transcript file if present: <media>.txt
        sidecar = source_path.with_suffix(source_path.suffix + ".txt")
        if sidecar.exists():
            return sidecar.read_text(encoding="utf-8", errors="ignore").strip()
        raise RuntimeError(
            f"No transcript sidecar found for {source_type} file. "
            f"Expected: {sidecar.name}. Add ASR integration for direct transcription."
        )

    return source_path.read_text(encoding="utf-8", errors="ignore").strip()


def _ensure_visualizer_fields(node: dict[str, Any]) -> None:
    if "cefr_level" not in node:
        node["cefr_level"] = "B1"
    if "linguistic_notes" not in node:
        node["linguistic_notes"] = ""
    if "translation" not in node or not isinstance(node.get("translation"), dict):
        node["translation"] = {"source_lang": "en", "target_lang": "ru", "text": ""}
    else:
        node["translation"].setdefault("source_lang", "en")
        node["translation"].setdefault("target_lang", "ru")
        node["translation"].setdefault("text", "")
    if "phonetic" not in node or not isinstance(node.get("phonetic"), dict):
        node["phonetic"] = {"uk": "", "us": ""}
    else:
        node["phonetic"].setdefault("uk", "")
        node["phonetic"].setdefault("us", "")

    for child in node.get("linguistic_elements", []) or []:
        if isinstance(child, dict):
            _ensure_visualizer_fields(child)


def run_media_pipeline(*, source_path: str, spacy_model: str = "en_core_web_sm") -> MediaPipelineResult:
    path = Path(source_path)
    if not path.exists():
        raise FileNotFoundError(f"Media source not found: {source_path}")

    source_type = _detect_source_type(path)
    full_text = _extract_text(path, source_type).strip()
    if not full_text:
        raise RuntimeError("Extracted text is empty.")

    nlp = load_nlp(spacy_model)
    skeleton = build_skeleton(full_text, nlp)
    analyzed = apply_tam(skeleton, nlp)

    media_sentences: list[dict[str, Any]] = []
    contract_sentences: list[dict[str, Any]] = []
    for idx, (sentence_text, sentence_node) in enumerate(analyzed.items()):
        _ensure_visualizer_fields(sentence_node)
        sent_hash = build_sentence_hash(sentence_text, idx)
        media_sentences.append(
            {
                "sentence_idx": idx,
                "sentence_text": sentence_text,
                "sentence_hash": sent_hash,
            }
        )
        contract_sentences.append(
            {
                "sentence_idx": idx,
                "sentence_hash": sent_hash,
                "sentence_node": sentence_node,
            }
        )

    text_hash = hashlib.sha256(full_text.encode("utf-8")).hexdigest()
    return MediaPipelineResult(
        source_type=source_type,
        full_text=full_text,
        text_hash=text_hash,
        media_sentences=media_sentences,
        contract_sentences=contract_sentences,
    )

