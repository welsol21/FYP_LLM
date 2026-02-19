"""Media extraction + contract build pipeline for runtime HTTP flow."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
from typing import Any

from ela_pipeline.client_storage import build_sentence_hash
from ela_pipeline.cefr import RuleBasedCEFRPredictor
from ela_pipeline.annotate.local_generator import LocalT5Annotator
from ela_pipeline.parse.spacy_parser import load_nlp
from ela_pipeline.phonetic import EspeakPhoneticTranscriber
from ela_pipeline.skeleton.builder import build_skeleton
from ela_pipeline.tam.rules import apply_tam
from ela_pipeline.translate import M2M100Translator

DEFAULT_LOCAL_TRANSLATION_MODEL_DIR = "artifacts/models/m2m100_418M"


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
        node["linguistic_notes"] = []
    if "translation" not in node or not isinstance(node.get("translation"), dict):
        node["translation"] = {"source_lang": "en", "target_lang": "ru", "text": str(node.get("content") or "")}
    else:
        node["translation"].setdefault("source_lang", "en")
        node["translation"].setdefault("target_lang", "ru")
        node["translation"].setdefault("text", str(node.get("content") or ""))
    if "phonetic" not in node or not isinstance(node.get("phonetic"), dict):
        node["phonetic"] = {"uk": "", "us": ""}
    else:
        node["phonetic"].setdefault("uk", "")
        node["phonetic"].setdefault("us", "")

    for child in node.get("linguistic_elements", []) or []:
        if isinstance(child, dict):
            _ensure_visualizer_fields(child)


class _EchoTranslator:
    """Safe translation fallback used when model-based translation is unavailable."""

    model_name = "echo"

    def translate_text(self, text: str, source_lang: str, target_lang: str) -> str:  # noqa: ARG002
        return (text or "").strip()


def _resolve_media_translator() -> Any:
    provider = os.getenv("ELA_MEDIA_TRANSLATION_PROVIDER", "echo").strip().lower()
    if provider != "m2m100":
        return _EchoTranslator()

    model_name = os.getenv("ELA_MEDIA_TRANSLATION_MODEL", "").strip() or "facebook/m2m100_418M"
    if model_name == "facebook/m2m100_418M" and os.path.isdir(DEFAULT_LOCAL_TRANSLATION_MODEL_DIR):
        model_name = DEFAULT_LOCAL_TRANSLATION_MODEL_DIR
    device = os.getenv("ELA_MEDIA_TRANSLATION_DEVICE", "cpu").strip() or "cpu"

    try:
        return M2M100Translator(model_name=model_name, device=device)
    except Exception:
        return _EchoTranslator()


def _walk_nodes(node: dict[str, Any]):
    yield node
    for child in node.get("linguistic_elements", []) or []:
        if isinstance(child, dict):
            yield from _walk_nodes(child)


def _attach_translation_runtime(
    analyzed: dict[str, Any],
    *,
    translator: Any,
    source_lang: str,
    target_lang: str,
) -> None:
    for sentence_node in analyzed.values():
        if not isinstance(sentence_node, dict):
            continue
        for node in _walk_nodes(sentence_node):
            source_text = str(node.get("content") or "").strip()
            translated = translator.translate_text(source_text, source_lang=source_lang, target_lang=target_lang)
            node["translation"] = {
                "source_lang": source_lang,
                "target_lang": target_lang,
                "text": translated,
            }


def _attach_phonetic_runtime(analyzed: dict[str, Any], *, transcriber: Any) -> None:
    for sentence_node in analyzed.values():
        if not isinstance(sentence_node, dict):
            continue
        for node in _walk_nodes(sentence_node):
            source_text = str(node.get("content") or "").strip()
            node["phonetic"] = {
                "uk": transcriber.transcribe_text(source_text, accent="uk"),
                "us": transcriber.transcribe_text(source_text, accent="us"),
            }


def _attach_cefr_runtime(analyzed: dict[str, Any], *, predictor: Any) -> None:
    for sentence_node in analyzed.values():
        if not isinstance(sentence_node, dict):
            continue
        sentence_text = str(sentence_node.get("content") or "")
        for node in _walk_nodes(sentence_node):
            source_text = str(node.get("content") or "")
            node["cefr_level"] = str(predictor.predict_level(node, source_text, sentence_text)).strip().upper() or "B1"


def _enrich_analyzed_contract(analyzed: dict[str, Any]) -> None:
    # Notes: deterministic template/rule mode, no model dependency required.
    annotator = LocalT5Annotator(model_dir=".", note_mode="template_only")
    annotator.annotate(analyzed)

    # CEFR: deterministic rule predictor for stable runtime behavior.
    _attach_cefr_runtime(analyzed, predictor=RuleBasedCEFRPredictor())

    # Translation: backend provider if configured, with safe echo fallback.
    translator = _resolve_media_translator()
    _attach_translation_runtime(
        analyzed,
        translator=translator,
        source_lang=os.getenv("ELA_MEDIA_TRANSLATION_SOURCE_LANG", "en"),
        target_lang=os.getenv("ELA_MEDIA_TRANSLATION_TARGET_LANG", "ru"),
    )

    # Phonetic: backend only; if binary unavailable, keep empty values.
    try:
        transcriber = EspeakPhoneticTranscriber(binary=os.getenv("ELA_MEDIA_PHONETIC_BINARY", "auto"))
        _attach_phonetic_runtime(
            analyzed,
            transcriber=transcriber,
        )
    except Exception:
        pass


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
    sentence_stream = [str(text).strip() for text in skeleton.keys() if str(text).strip()]

    media_sentences: list[dict[str, Any]] = []
    contract_sentences: list[dict[str, Any]] = []
    for idx, sentence_text in enumerate(sentence_stream):
        sentence_payload = _build_sentence_contract_with_nlp(
            sentence_text=sentence_text,
            sentence_idx=idx,
            nlp=nlp,
        )
        sentence_node = sentence_payload["sentence_node"]
        sent_hash = sentence_payload["sentence_hash"]
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


def build_sentence_contract(
    *,
    sentence_text: str,
    sentence_idx: int = 0,
    spacy_model: str = "en_core_web_sm",
) -> dict[str, Any]:
    nlp = load_nlp(spacy_model)
    return _build_sentence_contract_with_nlp(
        sentence_text=sentence_text,
        sentence_idx=sentence_idx,
        nlp=nlp,
    )


def _build_sentence_contract_with_nlp(
    *,
    sentence_text: str,
    sentence_idx: int,
    nlp: Any,
) -> dict[str, Any]:
    text = (sentence_text or "").strip()
    if not text:
        raise ValueError("sentence_text must be non-empty")
    skeleton = build_skeleton(text, nlp)
    if not skeleton:
        raise RuntimeError("Unable to build sentence skeleton.")
    analyzed = apply_tam(skeleton, nlp)
    _enrich_analyzed_contract(analyzed)

    if text in analyzed:
        node = analyzed[text]
    else:
        node = next(iter(analyzed.values()))
        text = str(node.get("content") or text)

    _ensure_visualizer_fields(node)
    return {
        "sentence_text": text,
        "sentence_hash": build_sentence_hash(text, int(sentence_idx)),
        "sentence_node": node,
    }
