"""Media extraction + contract build pipeline for runtime HTTP flow."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
from typing import Any, Callable

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


def _estimate_sentence_duration_seconds(text: str) -> float:
    words = len(re.findall(r"\w+", text or "", flags=re.UNICODE))
    return float(max(1.0, min(8.0, 0.35 * words + 0.8)))


def _tokenize_semantic_units(text: str, *, start_sec: float, end_sec: float) -> list[dict[str, Any]]:
    tokens = re.findall(r"\d+|[A-Za-zА-Яа-яЁё]+|[^\w\s]", text or "", flags=re.UNICODE)
    if not tokens:
        return []

    span = max(end_sec - start_sec, 0.001)
    unit = span / max(len(tokens), 1)
    out: list[dict[str, Any]] = []
    for idx, tok in enumerate(tokens, start=1):
        tok_start = start_sec + (idx - 1) * unit
        tok_end = start_sec + idx * unit
        out.append(
            {
                "id": idx,
                "type": "number" if tok.isdigit() else ("word" if tok.isalpha() else "symbol"),
                "text": tok,
                "audio": {
                    "origin_start": round(tok_start, 3),
                    "origin_end": round(tok_end, 3),
                },
            }
        )
    return out


def _extract_translation_text(sentence_node: dict[str, Any]) -> str:
    tr = sentence_node.get("translation")
    if isinstance(tr, dict):
        return str(tr.get("text") or "").strip()
    return ""


def _extract_text_and_sentence_chunks(source_path: Path, source_type: str) -> tuple[str, list[dict[str, Any]]]:
    if source_type == "text":
        return source_path.read_text(encoding="utf-8", errors="ignore").strip(), []

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
        return "\n".join(chunks).strip(), []

    if source_type in {"audio", "video"}:
        model_name = os.getenv("ELA_MEDIA_ASR_MODEL", "base").strip() or "base"
        source_lang = os.getenv("ELA_MEDIA_ASR_SOURCE_LANG", "en").strip() or "en"
        try:
            import whisper  # type: ignore[import-not-found]
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                "Audio/video processing requires local ASR. Install `openai-whisper` for client pipeline."
            ) from exc
        model = whisper.load_model(model_name)
        result = model.transcribe(
            str(source_path),
            language=source_lang,
            word_timestamps=False,
            verbose=False,
        )
        segments: list[dict[str, Any]] = []
        texts: list[str] = []
        for seg in result.get("segments", []) or []:
            text = str(seg.get("text") or "").strip()
            if not text:
                continue
            start_sec = float(seg.get("start") or 0.0)
            end_sec = float(seg.get("end") or start_sec + _estimate_sentence_duration_seconds(text))
            segments.append(
                {
                    "sentence_text": text,
                    "start_sec": start_sec,
                    "end_sec": max(end_sec, start_sec + 0.2),
                }
            )
            texts.append(text)

        if not segments:
            raise RuntimeError("ASR produced no transcript segments for media file.")
        return " ".join(texts).strip(), segments

    return source_path.read_text(encoding="utf-8", errors="ignore").strip(), []


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


class _OpenAITranslator:
    model_name = "gpt-4o-mini"

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def translate_text(self, text: str, source_lang: str, target_lang: str) -> str:
        try:
            from openai import OpenAI  # type: ignore[import-not-found]
        except Exception as exc:
            raise RuntimeError("OpenAI provider requires `openai` package.") from exc
        client = OpenAI(api_key=self.api_key)
        prompt = f"Translate from {source_lang} to {target_lang}. Return only translation.\n\n{text}"
        resp = client.chat.completions.create(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
        )
        return str(resp.choices[0].message.content or "").strip()


class _DeepLTranslator:
    model_name = "deepl"

    def __init__(self, auth_key: str) -> None:
        self.auth_key = auth_key

    def translate_text(self, text: str, source_lang: str, target_lang: str) -> str:
        try:
            import deepl  # type: ignore[import-not-found]
        except Exception as exc:
            raise RuntimeError("DeepL provider requires `deepl` package.") from exc
        tr = deepl.Translator(self.auth_key)
        return str(
            tr.translate_text(
                text,
                source_lang=source_lang.upper(),
                target_lang=target_lang.upper(),
            ).text
        ).strip()


def _lara_locale(lang: str) -> str:
    value = str(lang or "").strip().lower()
    mapping = {
        "en": "en-US",
        "ru": "ru-RU",
        "uk": "uk-UA",
        "de": "de-DE",
        "fr": "fr-FR",
        "es": "es-ES",
        "it": "it-IT",
        "pt": "pt-PT",
        "pl": "pl-PL",
        "tr": "tr-TR",
    }
    return mapping.get(value, f"{value}-{value.upper()}") if value else "en-US"


class _LaraTranslator:
    model_name = "lara"

    def __init__(self, api_id: str, api_secret: str) -> None:
        self.api_id = api_id
        self.api_secret = api_secret

    def translate_text(self, text: str, source_lang: str, target_lang: str) -> str:
        try:
            from lara_sdk import Credentials, Translator as LaraTranslator  # type: ignore[import-not-found]
        except Exception as exc:
            raise RuntimeError("Lara provider requires `lara-sdk` package.") from exc
        creds = Credentials(self.api_id, self.api_secret)
        client = LaraTranslator(creds)
        response = client.translate(
            text,
            source=_lara_locale(source_lang),
            target=_lara_locale(target_lang),
        )
        translated = getattr(response, "translation", "")
        return str(translated or "").strip()


def _resolve_media_translator(
    *,
    provider_override: str | None = None,
    provider_credentials: dict[str, str] | None = None,
) -> Any:
    provider = str(provider_override or os.getenv("ELA_MEDIA_TRANSLATION_PROVIDER", "echo")).strip().lower()
    creds = provider_credentials or {}
    if provider in {"original", "echo", "none"}:
        return _EchoTranslator()
    if provider == "gpt":
        key = str(creds.get("api_key") or os.getenv("OPENAI_API_KEY") or "").strip()
        if not key:
            raise RuntimeError("OpenAI provider selected but API key is missing.")
        return _OpenAITranslator(key)
    if provider == "deepl":
        key = str(creds.get("auth_key") or os.getenv("DEEPL_AUTH_KEY") or "").strip()
        if not key:
            raise RuntimeError("DeepL provider selected but auth key is missing.")
        return _DeepLTranslator(key)
    if provider == "lara":
        api_id = str(creds.get("api_id") or os.getenv("LARA_API_ID") or "").strip()
        api_secret = str(creds.get("api_secret") or os.getenv("LARA_API_SECRET") or "").strip()
        if not api_id or not api_secret:
            raise RuntimeError("Lara provider selected but API credentials are missing.")
        return _LaraTranslator(api_id=api_id, api_secret=api_secret)

    model_name = os.getenv("ELA_MEDIA_TRANSLATION_MODEL", "").strip() or (
        "facebook/m2m100_418M" if provider in {"m2m100", "hf"} else provider
    )
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


def _enrich_analyzed_contract(
    analyzed: dict[str, Any],
    *,
    translation_provider: str | None = None,
    provider_credentials: dict[str, str] | None = None,
) -> None:
    # Notes: deterministic template/rule mode, no model dependency required.
    annotator = LocalT5Annotator(model_dir=".", note_mode="template_only")
    annotator.annotate(analyzed)

    # CEFR: deterministic rule predictor for stable runtime behavior.
    _attach_cefr_runtime(analyzed, predictor=RuleBasedCEFRPredictor())

    # Translation: backend provider if configured, with safe echo fallback.
    translator = _resolve_media_translator(
        provider_override=translation_provider,
        provider_credentials=provider_credentials,
    )
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


def run_media_pipeline(
    *,
    source_path: str,
    spacy_model: str = "en_core_web_sm",
    sentence_contract_builder: Callable[..., dict[str, Any]] | None = None,
) -> MediaPipelineResult:
    path = Path(source_path)
    if not path.exists():
        raise FileNotFoundError(f"Media source not found: {source_path}")

    source_type = _detect_source_type(path)
    full_text, extracted_sentence_chunks = _extract_text_and_sentence_chunks(path, source_type)
    full_text = full_text.strip()
    if not full_text:
        raise RuntimeError("Extracted text is empty.")

    nlp = load_nlp(spacy_model)
    sentence_stream: list[str] = []
    sentence_timeline: list[dict[str, float] | None] = []
    if extracted_sentence_chunks:
        for row in extracted_sentence_chunks:
            text = str(row.get("sentence_text") or "").strip()
            if not text:
                continue
            sentence_stream.append(text)
            sentence_timeline.append(
                {
                    "start_sec": float(row.get("start_sec") or 0.0),
                    "end_sec": float(row.get("end_sec") or 0.0),
                }
            )
    else:
        skeleton = build_skeleton(full_text, nlp)
        sentence_stream = [str(text).strip() for text in skeleton.keys() if str(text).strip()]
        sentence_timeline = [None] * len(sentence_stream)

    media_sentences: list[dict[str, Any]] = []
    contract_sentences: list[dict[str, Any]] = []
    time_cursor_sec = 0.0
    for idx, sentence_text in enumerate(sentence_stream):
        if sentence_contract_builder is None:
            sentence_payload = _build_sentence_contract_with_nlp(
                sentence_text=sentence_text,
                sentence_idx=idx,
                nlp=nlp,
            )
        else:
            sentence_payload = sentence_contract_builder(
                sentence_text=sentence_text,
                sentence_idx=idx,
            )
        sentence_node = sentence_payload["sentence_node"]
        sentence_text_resolved = str(sentence_payload.get("sentence_text") or sentence_text).strip()
        sent_hash = sentence_payload["sentence_hash"]
        timing = sentence_timeline[idx] if idx < len(sentence_timeline) else None
        if timing is not None:
            start_sec = float(timing.get("start_sec") or 0.0)
            end_sec = float(timing.get("end_sec") or start_sec + 0.2)
            if end_sec <= start_sec:
                end_sec = start_sec + _estimate_sentence_duration_seconds(sentence_text_resolved)
            time_cursor_sec = max(time_cursor_sec, end_sec + 0.2)
        else:
            start_sec = time_cursor_sec
            end_sec = start_sec + _estimate_sentence_duration_seconds(sentence_text_resolved)
            time_cursor_sec = end_sec + 0.2

        ru_text = _extract_translation_text(sentence_node)
        media_sentences.append(
            {
                "sentence_idx": idx,
                "sentence_text": sentence_text_resolved,
                "sentence_hash": sent_hash,
                "start_ms": int(round(start_sec * 1000)),
                "end_ms": int(round(end_sec * 1000)),
                "id": idx + 1,
                "text_eng": sentence_text_resolved,
                "units": _tokenize_semantic_units(
                    sentence_text_resolved,
                    start_sec=start_sec,
                    end_sec=end_sec,
                ),
                "start": round(start_sec, 3),
                "end": round(end_sec, 3),
                "text_ru": ru_text,
                "units_ru": _tokenize_semantic_units(
                    ru_text,
                    start_sec=start_sec,
                    end_sec=end_sec,
                ),
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
    translation_provider: str | None = None,
    provider_credentials: dict[str, str] | None = None,
) -> dict[str, Any]:
    nlp = load_nlp(spacy_model)
    return _build_sentence_contract_with_nlp(
        sentence_text=sentence_text,
        sentence_idx=sentence_idx,
        nlp=nlp,
        translation_provider=translation_provider,
        provider_credentials=provider_credentials,
    )


def _build_sentence_contract_with_nlp(
    *,
    sentence_text: str,
    sentence_idx: int,
    nlp: Any,
    translation_provider: str | None = None,
    provider_credentials: dict[str, str] | None = None,
) -> dict[str, Any]:
    text = (sentence_text or "").strip()
    if not text:
        raise ValueError("sentence_text must be non-empty")
    skeleton = build_skeleton(text, nlp)
    if not skeleton:
        raise RuntimeError("Unable to build sentence skeleton.")
    analyzed = apply_tam(skeleton, nlp)
    _enrich_analyzed_contract(
        analyzed,
        translation_provider=translation_provider,
        provider_credentials=provider_credentials,
    )

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
