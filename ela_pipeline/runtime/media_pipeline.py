"""Media extraction + contract build pipeline for runtime HTTP flow."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import hashlib
import os
from pathlib import Path
import re
import subprocess
import threading
import time
from typing import Any, Callable

from ela_pipeline.parse.spacy_parser import load_nlp
from ela_pipeline.skeleton.builder import build_skeleton
from ela_pipeline.translate import M2M100Translator

DEFAULT_LOCAL_TRANSLATION_MODEL_DIR = "artifacts/models/m2m100_418M"


def _runtime_downloads_disabled() -> bool:
    value = str(os.getenv("ELA_MEDIA_DISABLE_RUNTIME_DOWNLOADS", "0")).strip().lower()
    return value in {"1", "true", "yes", "on"}


@lru_cache(maxsize=4)
def _get_spacy_nlp_cached(model_name: str):
    return load_nlp(model_name)


@lru_cache(maxsize=3)
def _get_whisper_model_cached(model_name: str, asr_cache_dir: str):
    try:
        import whisper  # type: ignore[import-not-found]
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("Audio/video ASR component is unavailable in this build.") from exc
    return whisper.load_model(model_name, download_root=asr_cache_dir)


def warmup_media_models(
    *,
    spacy_model: str = "en_core_web_sm",
    warmup_asr: bool = True,
    warmup_translation: bool = True,
) -> None:
    """Preload runtime media models so first user request avoids cold starts."""
    _get_spacy_nlp_cached(spacy_model)
    if not warmup_asr:
        pass
    else:
        model_name = os.getenv("ELA_MEDIA_ASR_MODEL", "base").strip() or "base"
        asr_cache_dir = Path(
            os.getenv("ELA_MEDIA_ASR_CACHE_DIR", "artifacts/models/whisper")
        ).resolve()
        asr_cache_dir.mkdir(parents=True, exist_ok=True)
        if _runtime_downloads_disabled():
            expected_model_path = asr_cache_dir / f"{model_name}.pt"
            if not expected_model_path.is_file():
                raise RuntimeError(
                    f"ASR model '{model_name}' is not bundled. Expected local file: {expected_model_path}."
                )
        _get_whisper_model_cached(model_name, str(asr_cache_dir))

    if not warmup_translation:
        return

    provider = str(os.getenv("ELA_MEDIA_TRANSLATION_PROVIDER", "m2m100")).strip().lower() or "m2m100"
    if provider not in {"m2m100", "hf"}:
        return

    model_name = os.getenv("ELA_MEDIA_TRANSLATION_MODEL", "").strip() or "facebook/m2m100_418M"
    if model_name == "facebook/m2m100_418M" and os.path.isdir(DEFAULT_LOCAL_TRANSLATION_MODEL_DIR):
        model_name = DEFAULT_LOCAL_TRANSLATION_MODEL_DIR
    device = os.getenv("ELA_MEDIA_TRANSLATION_DEVICE", "cpu").strip() or "cpu"
    if _runtime_downloads_disabled() and model_name == "facebook/m2m100_418M":
        raise RuntimeError(
            f"Translation model is not bundled. Expected local directory: {DEFAULT_LOCAL_TRANSLATION_MODEL_DIR}."
        )
    _get_m2m100_media_translator_cached(model_name, device)


@dataclass(frozen=True)
class MediaPipelineResult:
    source_type: str
    full_text: str
    text_hash: str
    media_sentences: list[dict[str, Any]]
    contract_sentences: list[dict[str, Any]]


@dataclass(frozen=True)
class MediaExtractionResult:
    """Result of the immutable (Whisper/text-extract) stage only.

    Stored as a checkpoint so that a failed contract-build step can be retried
    without repeating the expensive Whisper transcription.
    """

    source_type: str
    full_text: str
    sentence_stream: list[str]
    sentence_timeline: list[dict[str, float] | None]


def _detect_source_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md", ".rtf"}:
        return "text"
    if suffix in {".pdf"}:
        return "pdf"
    if suffix in {".docx", ".doc"}:
        return "docx"
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
    translations = sentence_node.get("translations")
    if isinstance(translations, dict):
        preferred = translations.get("m2m100")
        if isinstance(preferred, dict):
            text = str(preferred.get("text") or "").strip()
            if text:
                return text
        for row in translations.values():
            if isinstance(row, dict):
                text = str(row.get("text") or "").strip()
                if text:
                    return text
    return ""


_BIBLIOGRAPHIC_MARKERS = (
    "written by",
    "translated by",
    "translated from",
    "read by",
    "narrated by",
    "performed by",
    "adapted by",
    "illustrated by",
    "edited by",
    "published by",
    "produced by",
)


def _has_finite_verb(doc: Any) -> bool:
    for token in doc:
        if token.pos_ not in {"VERB", "AUX"}:
            continue
        verb_form = str(token.morph.get("VerbForm")[0]) if token.morph.get("VerbForm") else ""
        if verb_form == "Fin":
            return True
    return False


def _is_heading_like(doc: Any) -> bool:
    alpha_tokens = [tok for tok in doc if tok.is_alpha]
    if not alpha_tokens or len(alpha_tokens) > 8:
        return False
    if _has_finite_verb(doc):
        return False

    allowed_pos = {"NOUN", "PROPN", "ADJ", "ADP", "DET", "NUM", "CCONJ"}
    disallowed_pos = {"PRON", "VERB", "AUX", "SCONJ"}
    allowed = 0
    for token in alpha_tokens:
        if token.pos_ in disallowed_pos:
            return False
        if token.pos_ in allowed_pos:
            allowed += 1
    return allowed >= max(2, len(alpha_tokens) - 1)


def _is_metadata_like_sentence(text: str, doc: Any) -> bool:
    normalized = " ".join(str(text or "").strip().split())
    if not normalized:
        return True
    lower = normalized.casefold()

    if any(marker in lower for marker in _BIBLIOGRAPHIC_MARKERS) and not _has_finite_verb(doc):
        return True

    if _is_heading_like(doc):
        return True

    return False


def _probe_media_duration_seconds(source_path: Path) -> float:
    try:
        proc = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(source_path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        value = float((proc.stdout or "").strip() or "0")
        return max(0.0, value)
    except Exception:
        return 0.0


def _extract_text_and_sentence_chunks(
    source_path: Path,
    source_type: str,
    *,
    progress_callback: Callable[[str, float | None, str | None], None] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
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

    if source_type == "docx":
        try:
            import docx as _docx  # type: ignore[import-not-found]
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("DOCX extraction requires `python-docx` dependency.") from exc
        doc = _docx.Document(str(source_path))
        paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
        return "\n".join(paragraphs).strip(), []

    if source_type in {"audio", "video"}:
        model_name = os.getenv("ELA_MEDIA_ASR_MODEL", "base").strip() or "base"
        source_lang = os.getenv("ELA_MEDIA_ASR_SOURCE_LANG", "en").strip() or "en"
        asr_cache_dir = Path(
            os.getenv("ELA_MEDIA_ASR_CACHE_DIR", "artifacts/models/whisper")
        ).resolve()
        asr_cache_dir.mkdir(parents=True, exist_ok=True)
        if _runtime_downloads_disabled():
            expected_model_path = asr_cache_dir / f"{model_name}.pt"
            if not expected_model_path.is_file():
                raise RuntimeError(
                    f"ASR model '{model_name}' is not bundled. "
                    f"Expected local file: {expected_model_path}. "
                    "Runtime downloads are disabled."
                )
        if progress_callback is not None:
            progress_callback("transcribing_audio", 0.05, f"Loading ASR model: {model_name}")
        model = _get_whisper_model_cached(model_name, str(asr_cache_dir))
        media_duration_sec = _probe_media_duration_seconds(source_path)

        # Validate that the file actually contains audio before handing it to Whisper.
        # whisper.load_audio() uses ffmpeg internally; if the file contains no decodable
        # audio the subsequent mel-spectrogram reshape raises an opaque tensor error.
        # We load once here, validate, then pass the numpy array directly to transcribe
        # to avoid a second load that could return a different (empty) result.
        _WHISPER_SAMPLE_RATE = 16_000
        _MIN_AUDIO_SAMPLES = _WHISPER_SAMPLE_RATE // 10  # 100 ms minimum
        try:
            import whisper as _whisper_mod  # type: ignore[import-not-found]
            _raw = _whisper_mod.load_audio(str(source_path))
            n_samples = len(_raw) if _raw is not None and hasattr(_raw, "__len__") else 0
            if n_samples == 0:
                raise RuntimeError(
                    f"'{source_path.name}' contains no audio samples. "
                    "The file may have no audio track or may be corrupt."
                )
            if n_samples < _MIN_AUDIO_SAMPLES:
                raise RuntimeError(
                    f"'{source_path.name}' is too short for transcription "
                    f"({n_samples} samples, minimum {_MIN_AUDIO_SAMPLES})."
                )
        except RuntimeError:
            raise
        except Exception as _audio_exc:
            raise RuntimeError(
                f"Could not load audio from '{source_path.name}': {_audio_exc}"
            ) from _audio_exc

        result_holder: dict[str, Any] = {}
        error_holder: dict[str, Exception] = {}

        def _run_transcribe() -> None:
            try:
                # Pass the pre-loaded numpy array to avoid Whisper reloading the file.
                result_holder["result"] = model.transcribe(
                    _raw,
                    language=source_lang,
                    word_timestamps=False,
                    verbose=False,
                    fp16=False,
                )
            except Exception as exc:  # pragma: no cover
                error_holder["error"] = exc

        worker = threading.Thread(target=_run_transcribe, daemon=True)
        worker.start()
        started = time.monotonic()
        while worker.is_alive():
            worker.join(timeout=0.8)
            if progress_callback is None:
                continue
            elapsed = max(0.0, time.monotonic() - started)
            if media_duration_sec > 0:
                ratio = min(0.92, 0.08 + (elapsed / max(media_duration_sec * 1.25, 8.0)) * 0.84)
            else:
                ratio = min(0.92, 0.08 + min(elapsed / 90.0, 1.0) * 0.84)
            progress_callback("transcribing_audio", ratio, "ASR running...")

        if "error" in error_holder:
            raise RuntimeError(str(error_holder["error"])) from error_holder["error"]
        result = result_holder.get("result") or {}
        if progress_callback is not None:
            progress_callback("transcribing_audio", 1.0, "ASR completed.")
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


def _sentenceize_timed_chunks(
    *,
    chunks: list[dict[str, Any]],
    nlp: Any,
) -> tuple[list[str], list[dict[str, float] | None]]:
    normalized_chunks: list[dict[str, Any]] = []
    for row in chunks:
        text = str(row.get("sentence_text") or "").strip()
        if not text:
            continue
        normalized_chunks.append(
            {
                "sentence_text": " ".join(text.split()),
                "start_sec": float(row.get("start_sec") or 0.0),
                "end_sec": float(row.get("end_sec") or 0.0),
            }
        )
    if not normalized_chunks:
        return [], []

    merged_parts: list[str] = []
    char_ranges: list[dict[str, float | int]] = []
    cursor = 0
    for row in normalized_chunks:
        if merged_parts:
            merged_parts.append(" ")
            cursor += 1
        text = str(row["sentence_text"])
        start_char = cursor
        merged_parts.append(text)
        cursor += len(text)
        char_ranges.append(
            {
                "start_char": start_char,
                "end_char": cursor,
                "start_sec": float(row["start_sec"]),
                "end_sec": float(row["end_sec"]),
            }
        )
    merged_text = "".join(merged_parts).strip()
    if not merged_text:
        return [], []

    doc = nlp(merged_text)
    sentence_stream: list[str] = []
    sentence_timeline: list[dict[str, float] | None] = []
    for sent in doc.sents:
        sentence_text = str(sent.text or "").strip()
        if not sentence_text:
            continue
        start_char = int(sent.start_char)
        end_char = int(sent.end_char)
        overlaps = [
            row
            for row in char_ranges
            if int(row["end_char"]) > start_char and int(row["start_char"]) < end_char
        ]
        if overlaps:
            start_sec = float(overlaps[0]["start_sec"])
            end_sec = max(float(item["end_sec"]) for item in overlaps)
            if end_sec <= start_sec:
                end_sec = start_sec + _estimate_sentence_duration_seconds(sentence_text)
            sentence_timeline.append({"start_sec": start_sec, "end_sec": end_sec})
        else:
            sentence_timeline.append(None)
        sentence_stream.append(sentence_text)
    return sentence_stream, sentence_timeline


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

    def _client(self):  # type: ignore[return]
        try:
            from lara_sdk import Credentials, Translator as LaraTranslator  # type: ignore[import-not-found]
        except Exception as exc:
            raise RuntimeError("Lara provider requires `lara-sdk` package.") from exc
        return LaraTranslator(Credentials(self.api_id, self.api_secret))

    def translate_text(self, text: str, source_lang: str, target_lang: str) -> str:
        response = self._client().translate(
            text,
            source=_lara_locale(source_lang),
            target=_lara_locale(target_lang),
        )
        translated = getattr(response, "translation", "")
        return str(translated or "").strip()

    def translate_texts_batch(self, texts: list[str], source_lang: str, target_lang: str) -> dict[str, str]:
        response = self._client().translate(
            texts,
            source=_lara_locale(source_lang),
            target=_lara_locale(target_lang),
        )
        translations = response.translation  # List[str] when input is List[str]
        if isinstance(translations, str):
            translations = [translations]
        return {text: str(tr or "").strip() for text, tr in zip(texts, translations)}


@lru_cache(maxsize=8)
@lru_cache(maxsize=2)
def _get_m2m100_media_translator_cached(model_name: str, device: str) -> M2M100Translator:
    return M2M100Translator(model_name=model_name, device=device)


_m2m100_lock = threading.Lock()


def _resolve_media_translator(
    *,
    provider_override: str | None = None,
    provider_credentials: dict[str, str] | None = None,
) -> Any:
    provider = str(provider_override or os.getenv("ELA_MEDIA_TRANSLATION_PROVIDER", "echo")).strip().lower()
    creds = provider_credentials or {}
    downloads_disabled = _runtime_downloads_disabled()
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
    if downloads_disabled and model_name == "facebook/m2m100_418M":
        raise RuntimeError(
            f"Translation model is not bundled. Expected local directory: {DEFAULT_LOCAL_TRANSLATION_MODEL_DIR}. "
            "Runtime downloads are disabled."
        )
    if downloads_disabled and os.path.sep in model_name and not os.path.isdir(model_name):
        raise RuntimeError(
            f"Translation model path does not exist: {model_name}. Runtime downloads are disabled."
        )
    device = os.getenv("ELA_MEDIA_TRANSLATION_DEVICE", "cpu").strip() or "cpu"

    try:
        if downloads_disabled:
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
            os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
        return _get_m2m100_media_translator_cached(model_name, device)
    except Exception:
        if downloads_disabled:
            raise
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
            node["translations"] = {
                "m2m100": {
                    "source_lang": source_lang,
                    "target_lang": target_lang,
                    "text": translated or source_text,
                }
            }
            node["active_translation_provider"] = "m2m100"


def apply_translation_to_sentence_node(
    *,
    sentence_node: dict[str, Any],
    translation_provider: str | None = None,
    provider_credentials: dict[str, str] | None = None,
    source_lang: str | None = None,
    target_lang: str | None = None,
) -> None:
    translator = _resolve_media_translator(
        provider_override=translation_provider,
        provider_credentials=provider_credentials,
    )
    source_lang_resolved = source_lang or os.getenv("ELA_MEDIA_TRANSLATION_SOURCE_LANG", "en")
    target_lang_resolved = target_lang or os.getenv("ELA_MEDIA_TRANSLATION_TARGET_LANG", "ru")

    existing_text_by_node_id: dict[int, str] = {}
    for node in _walk_nodes(sentence_node):
        translations = node.get("translations")
        if not isinstance(translations, dict):
            continue
        row = translations.get("m2m100")
        if isinstance(row, dict):
            existing_text_by_node_id[id(node)] = str(row.get("text") or "").strip()

    analyzed = {"_": sentence_node}
    _attach_translation_runtime(
        analyzed,
        translator=translator,
        source_lang=source_lang_resolved,
        target_lang=target_lang_resolved,
    )

    if str(source_lang_resolved).strip().lower() == str(target_lang_resolved).strip().lower():
        return

    for node in _walk_nodes(sentence_node):
        source_text = str(node.get("content") or "").strip()
        if not source_text:
            continue

        translations = node.get("translations")
        if not isinstance(translations, dict):
            continue
        tr = translations.get("m2m100")
        if not isinstance(tr, dict):
            continue

        new_text = str(tr.get("text") or "").strip()
        if not new_text:
            continue

        # If local provider returned unchanged source text, keep pre-existing backend translation.
        if new_text.casefold() == source_text.casefold():
            existing_translation = existing_text_by_node_id.get(id(node), "").strip()
            if existing_translation and existing_translation.casefold() != source_text.casefold():
                tr["text"] = existing_translation


def translate_text_with_provider(
    *,
    text: str,
    translation_provider: str | None = None,
    provider_credentials: dict[str, str] | None = None,
    source_lang: str | None = None,
    target_lang: str | None = None,
) -> str:
    source_text = str(text or "").strip()
    if not source_text:
        return ""
    translator = _resolve_media_translator(
        provider_override=translation_provider,
        provider_credentials=provider_credentials,
    )
    source_lang_resolved = source_lang or os.getenv("ELA_MEDIA_TRANSLATION_SOURCE_LANG", "en")
    target_lang_resolved = target_lang or os.getenv("ELA_MEDIA_TRANSLATION_TARGET_LANG", "ru")
    lock = _m2m100_lock if isinstance(translator, M2M100Translator) else None
    if lock:
        with lock:
            return str(translator.translate_text(source_text, source_lang=source_lang_resolved, target_lang=target_lang_resolved) or "").strip()
    return str(
        translator.translate_text(source_text, source_lang=source_lang_resolved, target_lang=target_lang_resolved) or ""
    ).strip()


def translate_texts_with_provider(
    texts: "list[str]",
    *,
    translation_provider: "str | None" = None,
    provider_credentials: "dict[str, str] | None" = None,
    source_lang: "str | None" = None,
    target_lang: "str | None" = None,
) -> "dict[str, str]":
    """Translate a batch of texts, returning {original_text: translated_text}.

    Uses native batch APIs where available (M2M100 single generate call,
    Lara single HTTP call). Falls back to sequential translate_text_with_provider
    for other providers.
    """
    unique: list[str] = list(dict.fromkeys(t.strip() for t in texts if t.strip()))
    if not unique:
        return {}
    source_lang_resolved = source_lang or os.getenv("ELA_MEDIA_TRANSLATION_SOURCE_LANG", "en")
    target_lang_resolved = target_lang or os.getenv("ELA_MEDIA_TRANSLATION_TARGET_LANG", "ru")
    translator = _resolve_media_translator(
        provider_override=translation_provider,
        provider_credentials=provider_credentials,
    )
    if isinstance(translator, M2M100Translator):
        # Lowercase input so M2M100 doesn't treat capitalised words as proper nouns
        # and refuses to translate them. Map results back to original casing.
        lowered = [t.lower() for t in unique]
        BATCH_SIZE = 16
        all_results: list[str] = []
        with _m2m100_lock:
            for i in range(0, len(lowered), BATCH_SIZE):
                chunk = lowered[i:i + BATCH_SIZE]
                all_results.extend(translator.translate_texts(chunk, source_lang=source_lang_resolved, target_lang=target_lang_resolved))
        return {orig: tr for orig, tr in zip(unique, all_results)}
    if isinstance(translator, _LaraTranslator):
        return translator.translate_texts_batch(unique, source_lang=source_lang_resolved, target_lang=target_lang_resolved)
    # Other providers: sequential
    out: dict[str, str] = {}
    for text in unique:
        out[text] = str(translator.translate_text(text, source_lang=source_lang_resolved, target_lang=target_lang_resolved) or "").strip()
    return out


def extract_media_text_and_sentences(
    *,
    source_path: str,
    spacy_model: str = "en_core_web_sm",
    progress_callback: Callable[[str, float | None, str | None], None] | None = None,
) -> MediaExtractionResult:
    """Immutable stage: run Whisper (or text/PDF extract) and split into sentences.

    This is the expensive step.  Its result is checkpointed by the service layer
    so that a subsequent contract-build failure does not require repeating it.
    """
    path = Path(source_path)
    if not path.exists():
        raise FileNotFoundError(f"Media source not found: {source_path}")

    source_type = _detect_source_type(path)
    full_text, extracted_sentence_chunks = _extract_text_and_sentence_chunks(
        path,
        source_type,
        progress_callback=progress_callback,
    )
    full_text = full_text.strip()
    if not full_text:
        raise RuntimeError("Extracted text is empty.")

    if progress_callback is not None:
        progress_callback("translating_text", 0.02, "Preparing linguistic parsing")
    nlp = _get_spacy_nlp_cached(spacy_model)
    if progress_callback is not None:
        progress_callback("translating_text", 0.04, "Splitting transcript into sentences")
    sentence_stream: list[str] = []
    sentence_timeline: list[dict[str, float] | None] = []
    if extracted_sentence_chunks:
        # Keep ASR chunk timing intact for media pipeline.
        # The 2026-02-24 backend path used Whisper segments directly here,
        # and later subtitle/audio assembly relied on those original windows.
        # Re-sentenceizing via spaCy shifts sentence boundaries and breaks
        # subtitle timing in generated video.
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
        fallback_stream = [str(text or "").strip() for text in skeleton.keys() if str(text or "").strip()]
        for text in skeleton.keys():
            text_resolved = str(text).strip()
            if not text_resolved:
                continue
            doc = nlp(text_resolved)
            if _is_metadata_like_sentence(text_resolved, doc):
                continue
            sentence_stream.append(text_resolved)
            sentence_timeline.append(None)
        if not sentence_stream:
            if fallback_stream:
                sentence_stream = fallback_stream
                sentence_timeline = [None for _ in fallback_stream]
            elif full_text:
                sentence_stream = [full_text]
                sentence_timeline = [None]

    if progress_callback is not None:
        progress_callback("translating_text", 0.08, f"Prepared {len(sentence_stream)} sentences")

    return MediaExtractionResult(
        source_type=source_type,
        full_text=full_text,
        sentence_stream=sentence_stream,
        sentence_timeline=sentence_timeline,
    )


def build_media_contracts(
    *,
    extraction: MediaExtractionResult,
    sentence_contract_builder: Callable[..., dict[str, Any]],
    progress_callback: Callable[[str, float | None, str | None], None] | None = None,
) -> MediaPipelineResult:
    """Variant stage: call sentence_contract_builder for every extracted sentence."""
    source_type = extraction.source_type
    full_text = extraction.full_text
    sentence_stream = extraction.sentence_stream
    sentence_timeline = extraction.sentence_timeline

    media_sentences: list[dict[str, Any]] = []
    contract_sentences: list[dict[str, Any]] = []
    time_cursor_sec = 0.0
    total_sentences = max(len(sentence_stream), 1)

    for idx, sentence_text in enumerate(sentence_stream):
        if progress_callback is not None:
            progress_callback(
                "translating_text",
                idx / total_sentences,
                f"Building sentence contract {idx + 1}/{total_sentences}",
            )
        if sentence_contract_builder is None:
            raise RuntimeError("sentence_contract_builder is required.")
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
        if progress_callback is not None:
            progress_callback(
                "translating_text",
                (idx + 1) / total_sentences,
                f"Built sentence contract {idx + 1}/{total_sentences}",
            )

    text_hash = hashlib.sha256(full_text.encode("utf-8")).hexdigest()
    return MediaPipelineResult(
        source_type=source_type,
        full_text=full_text,
        text_hash=text_hash,
        media_sentences=media_sentences,
        contract_sentences=contract_sentences,
    )


def run_media_pipeline(
    *,
    source_path: str,
    spacy_model: str = "en_core_web_sm",
    sentence_contract_builder: Callable[..., dict[str, Any]] | None = None,
    progress_callback: Callable[[str, float | None, str | None], None] | None = None,
) -> MediaPipelineResult:
    """Convenience wrapper: extract + build contracts in one call (no checkpoint)."""
    if sentence_contract_builder is None:
        raise RuntimeError(
            "sentence_contract_builder is required. Local sentence-contract fallback is disabled."
        )
    extraction = extract_media_text_and_sentences(
        source_path=source_path,
        spacy_model=spacy_model,
        progress_callback=progress_callback,
    )
    return build_media_contracts(
        extraction=extraction,
        sentence_contract_builder=sentence_contract_builder,
        progress_callback=progress_callback,
    )
