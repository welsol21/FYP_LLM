"""Lightweight HTTP bridge for frontend -> runtime service."""

from __future__ import annotations

import json
import os
import cgi
import queue as _queue
import threading as _threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .media_pipeline import extract_media_text_and_sentences, warmup_media_models
from .service import RuntimeMediaService


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = str(raw).strip().lower()
    return value in {"1", "true", "yes", "on"}


def _env_str(name: str, default: str = "") -> str:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip()


def _resolve_classifier_settings() -> tuple[str, str | None]:
    provider_raw = _env_str("ELA_CLASSIFIER_PROVIDER", "").lower()
    model_path = _env_str("ELA_CLASSIFIER_MODEL_PATH", "")

    default_tabular_dirs = [
        "artifacts/models/tabular_joint_profile_full_ladder_xgboost_gpu_v2",
        "artifacts/models/tabular_joint_profile_random_forest_v1",
        "artifacts/models/tabular_cefr_baseline_full_ladder_xgboost_gpu_v1",
        "artifacts/models/tabular_cefr_baseline_full_ladder_random_forest_v2",
        "artifacts/models/tabular_cefr_baseline_full_ladder_random_forest",
        "artifacts/models/tabular_cefr_baseline_full_ladder_logreg",
    ]

    def _tabular_dir_ready(path: str) -> bool:
        return (
            os.path.isdir(path)
            and os.path.isfile(os.path.join(path, "classifier_metadata.json"))
            and (
                os.path.isfile(os.path.join(path, "best_tabular_joint_profile.joblib"))
                or os.path.isfile(os.path.join(path, "best_tabular_cefr_baseline.joblib"))
            )
        )

    default_tabular_dir = next(
        (candidate for candidate in default_tabular_dirs if _tabular_dir_ready(candidate)),
        default_tabular_dirs[0],
    )
    preferred_tabular_dir = default_tabular_dir

    if provider_raw:
        provider = provider_raw
    else:
        default_model_dir = "artifacts/models/deberta_classifier_cefr"
        has_tabular = _tabular_dir_ready(default_tabular_dir)
        has_deberta = (
            os.path.isdir(default_model_dir)
            and os.path.isfile(os.path.join(default_model_dir, "classifier_metadata.json"))
        )
        provider = "tabular" if has_tabular else ("deberta" if has_deberta else "rule")
        if not model_path and provider == "deberta":
            model_path = default_model_dir
        if not model_path and provider == "tabular":
            model_path = default_tabular_dir

    if provider == "deberta" and not model_path:
        model_path = "artifacts/models/deberta_classifier_cefr"
    if provider == "tabular" and not model_path:
        model_path = preferred_tabular_dir

    if provider not in {"rule", "deberta", "tabular"}:
        raise ValueError("ELA_CLASSIFIER_PROVIDER must be one of: rule | deberta | tabular")

    return provider, (model_path or None)


SERVICE = RuntimeMediaService(
    db_path=os.getenv("ELA_CLIENT_DB_PATH", "artifacts/client_state.sqlite3"),
    runtime_mode=os.getenv("ELA_RUNTIME_MODE", "auto"),
    deployment_mode=os.getenv("ELA_DEPLOYMENT_MODE", "auto"),
)


def _format_srt_time(ms: int) -> str:
    ms = max(0, int(ms))
    h, rem = divmod(ms, 3600000)
    m, rem = divmod(rem, 60000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _build_srt(sentences: list[dict], mode: str) -> str:
    blocks: list[str] = []
    cue = 1
    for sent in sentences:
        start_ms = max(0, int(sent.get("start_ms") or 0))
        end_ms = max(start_ms + 300, int(sent.get("end_ms") or 0))
        en = str(sent.get("text_eng") or "").strip()
        ru = str(sent.get("text_ru") or "").strip()
        ts = f"{_format_srt_time(start_ms)} --> {_format_srt_time(end_ms)}"
        if mode == "source":
            if en:
                blocks.append(f"{cue}\n{ts}\n{en}\n"); cue += 1
        elif mode == "target":
            if ru:
                blocks.append(f"{cue}\n{ts}\n{ru}\n"); cue += 1
        else:  # bilingual
            if en and ru:
                blocks.append(f"{cue}\n{ts}\n{en}\n{ru}\n"); cue += 1
            elif en:
                blocks.append(f"{cue}\n{ts}\n{en}\n"); cue += 1
            elif ru:
                blocks.append(f"{cue}\n{ts}\n{ru}\n"); cue += 1
    return "\n".join(blocks)


def _render_media_artifacts(sentences: list[dict], voice: str, subtitles_mode: str, need_audio: bool = True, need_video: bool = True, source_audio_bytes: bytes = b"") -> bytes:
    """Generate TTS → assemble bilingual audio → compose video → return ZIP bytes."""
    import asyncio
    import io
    import shutil
    import subprocess
    import tempfile
    import zipfile

    import numpy as np

    TARGET_RATE = 24000
    voice_name = "ru-RU-SvetlanaNeural" if voice.startswith("f") else "ru-RU-DmitryNeural"

    def _decode_audio(raw_bytes: bytes) -> np.ndarray:
        proc = subprocess.run(
            ["ffmpeg", "-i", "pipe:0", "-f", "f32le", "-ar", str(TARGET_RATE), "-ac", "1", "pipe:1"],
            input=raw_bytes, capture_output=True,
        )
        return np.frombuffer(proc.stdout, dtype=np.float32).copy()

    # ── 1. Decode source audio if provided ────────────────────────────────────
    source_pcm: "np.ndarray | None" = None
    if source_audio_bytes:
        try:
            source_pcm = _decode_audio(source_audio_bytes)
        except Exception:
            source_pcm = None

    # ── 2. Generate TTS (only if audio or video needed) ───────────────────────
    output_pcm: "np.ndarray | None" = None
    if need_audio or need_video:
        async def _tts(text: str, sem: asyncio.Semaphore) -> bytes:
            import edge_tts as _edge_tts
            async with sem:
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                    tmp = Path(f.name)
                try:
                    await _edge_tts.Communicate(text, voice_name).save(str(tmp))
                    return tmp.read_bytes()
                finally:
                    tmp.unlink(missing_ok=True)

        async def _generate_all() -> list[bytes]:
            sem = asyncio.Semaphore(8)
            async def _empty() -> bytes:
                return b""
            tasks = [
                _tts(str(s.get("text_ru") or ""), sem) if str(s.get("text_ru") or "").strip() else _empty()
                for s in sentences
            ]
            return list(await asyncio.gather(*tasks, return_exceptions=False))

        tts_blobs: list[bytes] = asyncio.run(_generate_all())
        tts_pcms: list["np.ndarray | None"] = [
            _decode_audio(b) if b else None for b in tts_blobs
        ]

        # ── 3. Assemble bilingual PCM; track output positions for video SRT ──────
        # video_srt_entries: (start_ms, end_ms, text) in OUTPUT audio time
        video_srt_entries: "list[tuple[int,int,str]]" = []
        en_out_entries:    "list[tuple[int,int,str]]" = []
        ru_out_entries:    "list[tuple[int,int,str]]" = []

        is_simultaneous = subtitles_mode == "bilingual_simultaneous"

        if source_pcm is not None and subtitles_mode not in ("target", "source"):
            # Bilingual assembly — exact match of reference generate_outputs():
            # • Start at first sentence (no pre-sentence gap)
            # • eng_audio → 10 ms silence → tts_audio per sentence
            # • Inter-sentence: 1/3-length silence
            # • No tail after last sentence
            # • Track EN and RU output positions separately for correct SRT/ASS
            chunks: list[np.ndarray] = []
            src_len = len(source_pcm)
            out_samples = 0  # running output position in samples
            SILENCE_10MS = int(0.01 * TARGET_RATE)  # 10 ms gap between eng and TTS

            # Per-sentence output-time entries for all three SRT variants
            en_out_entries:  "list[tuple[int,int,str]]" = []
            ru_out_entries:  "list[tuple[int,int,str]]" = []

            for idx, (sent, tts_pcm) in enumerate(zip(sentences, tts_pcms)):
                start_s = int(max(0, int(sent.get("start_ms") or 0)) / 1000 * TARGET_RATE)
                end_s = min(int(max(0, int(sent.get("end_ms") or 0)) / 1000 * TARGET_RATE), src_len)
                en = str(sent.get("text_eng") or "").strip()
                ru = str(sent.get("text_ru") or "").strip()

                # ── English source clip ──────────────────────────────────────
                pos_en = int(out_samples / TARGET_RATE * 1000)
                dur_e = 0
                if end_s > start_s:
                    seg = source_pcm[start_s:end_s]
                    chunks.append(seg)
                    out_samples += len(seg)
                    dur_e = len(seg)
                end_en_ms = int(out_samples / TARGET_RATE * 1000)

                # 10 ms silence between eng and TTS (matches reference)
                chunks.append(np.zeros(SILENCE_10MS, dtype=np.float32))
                out_samples += SILENCE_10MS

                # ── Russian TTS ──────────────────────────────────────────────
                pos_ru = int(out_samples / TARGET_RATE * 1000)
                dur_r = 0
                if tts_pcm is not None and len(tts_pcm) > 0:
                    chunks.append(tts_pcm)
                    out_samples += len(tts_pcm)
                    dur_r = len(tts_pcm)
                end_ru_ms = int(out_samples / TARGET_RATE * 1000)

                end_all_ms = end_ru_ms  # span covers eng + 10ms + tts

                # ── Subtitle entries at output positions ─────────────────────
                if is_simultaneous:
                    # EN top ({\an8}), RU bottom ({\an2}), same time span.
                    # Two separate ASS events — different screen positions.
                    if en:
                        video_srt_entries.append((pos_en, end_all_ms, r'{\an8}' + en))
                        en_out_entries.append((pos_en, end_all_ms, en))
                    if ru:
                        video_srt_entries.append((pos_en, end_all_ms, r'{\an2}' + ru))
                        ru_out_entries.append((pos_en, end_all_ms, ru))
                else:
                    # Sequential: EN during source clip (center), RU during TTS (center)
                    if en and dur_e > 0:
                        video_srt_entries.append((pos_en, end_en_ms, en))
                        en_out_entries.append((pos_en, end_en_ms, en))
                    if ru and dur_r > 0:
                        video_srt_entries.append((pos_ru, end_ru_ms, ru))
                        ru_out_entries.append((pos_ru, end_ru_ms, ru))

                # Inter-sentence gap → 1/3-length silence (matches reference)
                if idx < len(sentences) - 1:
                    next_start_s = int(max(0, int(sentences[idx + 1].get("start_ms") or 0)) / 1000 * TARGET_RATE)
                    gap_s = max(0, next_start_s - end_s)
                    silence_s = max(gap_s // 3, SILENCE_10MS)
                    chunks.append(np.zeros(silence_s, dtype=np.float32))
                    out_samples += silence_s

            output_pcm = np.concatenate(chunks) if chunks else source_pcm

        elif subtitles_mode == "source" and source_pcm is not None:
            output_pcm = source_pcm
            for sent in sentences:
                en = str(sent.get("text_eng") or "").strip()
                if en:
                    video_srt_entries.append((
                        max(0, int(sent.get("start_ms") or 0)),
                        max(300, int(sent.get("end_ms") or 0)),
                        en,
                    ))

        else:
            # Target-only: TTS at original sentence positions, no source audio
            output_pcm = np.zeros(TARGET_RATE, dtype=np.float32)
            for sent, tts_pcm in zip(sentences, tts_pcms):
                if tts_pcm is None:
                    continue
                start_sample = int(max(0, int(sent.get("start_ms") or 0)) / 1000 * TARGET_RATE)
                end_sample = start_sample + len(tts_pcm)
                if end_sample > len(output_pcm):
                    output_pcm = np.concatenate([output_pcm, np.zeros(end_sample - len(output_pcm), dtype=np.float32)])
                output_pcm[start_sample:end_sample] = tts_pcm
                ru = str(sent.get("text_ru") or "").strip()
                if ru:
                    video_srt_entries.append((
                        max(0, int(sent.get("start_ms") or 0)),
                        max(300, int(sent.get("end_ms") or 0)),
                        ru,
                    ))

    # ── 3. Encode assembled PCM → MP3 (needed for audio or video) ────────────
    mp3_bytes = b""
    if (need_audio or need_video) and output_pcm is not None:
        proc = subprocess.run(
            ["ffmpeg", "-f", "f32le", "-ar", str(TARGET_RATE), "-ac", "1", "-i", "pipe:0",
             "-c:a", "libmp3lame", "-q:a", "2", "-f", "mp3", "pipe:1"],
            input=output_pcm.tobytes(), capture_output=True, check=True,
        )
        mp3_bytes = proc.stdout

    # ── 4. Build SRT files ─────────────────────────────────────────────────────
    # For bilingual modes the output audio is compressed (no pre/post gaps,
    # 1/3 inter-sentence silence), so SRT must use output-relative positions.
    # For source/target modes the output audio preserves original timing.
    def _entries_to_srt(entries: "list[tuple[int,int,str]]") -> str:
        blocks = []
        for cue, (start_ms, end_ms, text) in enumerate(entries, 1):
            end_ms = max(start_ms + 300, end_ms)
            blocks.append(f"{cue}\n{_format_srt_time(start_ms)} --> {_format_srt_time(end_ms)}\n{text}\n")
        return "\n".join(blocks)

    if subtitles_mode not in ("source", "target"):
        # Build bilingual SRT: EN+RU per sentence at output positions
        bilingual_out_entries: "list[tuple[int,int,str]]" = []
        en_idx = ru_idx = 0
        while en_idx < len(en_out_entries) or ru_idx < len(ru_out_entries):
            en_e = en_out_entries[en_idx] if en_idx < len(en_out_entries) else None
            ru_e = ru_out_entries[ru_idx] if ru_idx < len(ru_out_entries) else None
            if en_e and ru_e and en_e[0] == ru_e[0]:
                # Simultaneous pair at same start time
                bilingual_out_entries.append((en_e[0], max(en_e[1], ru_e[1]), f"{en_e[2]}\n{ru_e[2]}"))
                en_idx += 1; ru_idx += 1
            elif en_e and (not ru_e or en_e[0] < ru_e[0]):
                bilingual_out_entries.append(en_e)
                en_idx += 1
            else:
                bilingual_out_entries.append(ru_e)  # type: ignore[arg-type]
                ru_idx += 1
        srt_en = _entries_to_srt(en_out_entries)
        srt_bilingual = _entries_to_srt(bilingual_out_entries)
        srt_target = _entries_to_srt(ru_out_entries)
    else:
        srt_en = _build_srt(sentences, "source")
        srt_bilingual = _build_srt(sentences, "bilingual")
        srt_target = _build_srt(sentences, "target")

    # Video subtitles use ASS format: supports Alignment=5 (middle-center) and \N\N (blank line)
    def _format_ass_time(ms: int) -> str:
        ms = max(0, int(ms))
        h, rem = divmod(ms, 3600000)
        m, rem = divmod(rem, 60000)
        s, ms_rem = divmod(rem, 1000)
        cs = ms_rem // 10
        return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

    def _entries_to_ass(entries: "list[tuple[int,int,str]]") -> str:
        header = (
            "[Script Info]\nScriptType: v4.00+\nPlayResX: 1280\nPlayResY: 720\n\n"
            "[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
            "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding\n"
            "Style: Default,DejaVu Sans,32,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,"
            "0,0,0,0,100,100,0,0,1,2,0,5,10,10,10,1\n\n"
            "[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        )
        lines = [header]
        for start_ms, end_ms, text in entries:
            end_ms = max(start_ms + 300, end_ms)
            ass_text = text.replace("\n", "\\N")
            lines.append(
                f"Dialogue: 0,{_format_ass_time(start_ms)},{_format_ass_time(end_ms)}"
                f",Default,,0,0,0,,{ass_text}\n"
            )
        return "".join(lines)

    selected_ass = _entries_to_ass(video_srt_entries)

    # ── 5. Compose video: static black frame + audio + subtitles ─────────────
    # Use -loop 1 with a single black image (matches reference), so -shortest
    # reliably terminates at the audio stream end without libass duration hints.
    mp4_bytes = b""
    if need_video:
        tmpdir = Path(tempfile.mkdtemp())
        try:
            audio_path = tmpdir / "audio.mp3"
            ass_path = tmpdir / "subs.ass"
            black_path = tmpdir / "black.png"
            video_path = tmpdir / "output.mp4"
            audio_path.write_bytes(mp3_bytes)
            ass_path.write_text(selected_ass, encoding="utf-8")

            # Generate single black 1280×720 frame
            subprocess.run(
                ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:size=1280x720",
                 "-vframes", "1", str(black_path)],
                capture_output=True, check=True,
            )

            # Compute exact audio duration from PCM to cap video precisely.
            # Neither -shortest nor lavfi duration hints are reliable when the
            # subtitles filter is in the pipeline — explicit -t is the only fix.
            audio_duration_s = len(output_pcm) / TARGET_RATE if output_pcm is not None else 0.0

            safe_ass = str(ass_path).replace("\\", "\\\\").replace(":", "\\:")
            vf = f"ass='{safe_ass}':fontsdir=/usr/share/fonts/truetype/dejavu"
            subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-loop", "1", "-framerate", "5", "-i", str(black_path),
                    "-i", str(audio_path),
                    "-t", f"{audio_duration_s:.3f}",
                    "-vf", vf,
                    "-map", "0:v", "-map", "1:a",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-preset", "ultrafast", "-tune", "stillimage", "-crf", "28",
                    "-c:a", "aac", "-b:a", "128k",
                    str(video_path),
                ],
                capture_output=True, check=True,
            )
            mp4_bytes = video_path.read_bytes()
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    # ── 6. Pack into ZIP (STORED — files already compressed) ──────────────────
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_STORED) as zf:
        if need_audio:
            zf.writestr("translated_audio_ru.mp3", mp3_bytes)
        if need_video:
            zf.writestr("translated_video_ru.mp4", mp4_bytes)
        zf.writestr("subtitles_en.srt", srt_en.encode("utf-8"))
        zf.writestr("subtitles_bilingual.srt", srt_bilingual.encode("utf-8"))
        zf.writestr("subtitles_target.srt", srt_target.encode("utf-8"))
    return buf.getvalue()


def _build_sentence_contract_payload(sentence_text: str, sentence_idx: int) -> dict:
    controlled_model_dir = _env_str("ELA_CONTROLLED_T5_MODEL_DIR", "")
    classifier_provider, classifier_model_path = _resolve_classifier_settings()
    return SERVICE.build_sentence_contract(
        sentence_text=sentence_text,
        sentence_idx=sentence_idx,
        note_mode="controlled",
        model_dir=controlled_model_dir or None,
        validation_mode="v2_strict",
        enable_translation=False,
        translation_model="artifacts/models/m2m100_418M",
        translation_source_lang="en",
        translation_target_lang="ru",
        translation_device="cpu",
        enable_phonetic=True,
        phonetic_binary="auto",
        enable_synonyms=False,
        synonyms_top_k=5,
        enable_cefr=(classifier_provider == "rule"),
        cefr_provider="rule",
        cefr_model_path="artifacts/models/t5_cefr/best_model",
        classifier_provider=classifier_provider,
        classifier_model_path=classifier_model_path,
        classifier_device="cuda",
        enable_grammar_classes=True,
    )


def _run_sentence_contract_warmup() -> None:
    if not _env_bool("ELA_SENTENCE_CONTRACT_WARMUP", True):
        print("[runtime-api] sentence-contract warmup disabled", flush=True)
        return
    warmup_text = str(
        os.getenv(
            "ELA_SENTENCE_CONTRACT_WARMUP_TEXT",
            "She should have trusted her instincts before making the decision.",
        )
    ).strip()
    if not warmup_text:
        print("[runtime-api] sentence-contract warmup skipped: empty warmup text", flush=True)
        return
    print("[runtime-api] sentence-contract warmup started", flush=True)
    try:
        _build_sentence_contract_payload(warmup_text, 0)
        print("[runtime-api] sentence-contract warmup completed", flush=True)
    except Exception as exc:
        # Keep API boot alive even if warmup failed; requests will return runtime error details.
        print(f"[runtime-api] sentence-contract warmup failed: {exc}", flush=True)


def _run_media_pipeline_warmup() -> None:
    if not _env_bool("ELA_MEDIA_PIPELINE_WARMUP", True):
        print("[runtime-api] media warmup disabled", flush=True)
        return
    warmup_asr = _env_bool("ELA_MEDIA_WARMUP_ASR", True)
    warmup_translation = _env_bool("ELA_MEDIA_WARMUP_TRANSLATION", True)
    print(
        f"[runtime-api] media warmup started "
        f"(asr={str(warmup_asr).lower()}, translation={str(warmup_translation).lower()})",
        flush=True,
    )
    try:
        warmup_media_models(
            spacy_model="en_core_web_sm",
            warmup_asr=warmup_asr,
            warmup_translation=warmup_translation,
        )
        print("[runtime-api] media warmup completed", flush=True)
    except Exception as exc:
        print(f"[runtime-api] media warmup failed: {exc}", flush=True)


class RuntimeApiHandler(BaseHTTPRequestHandler):
    server_version = "ELARuntimeHTTP/1.0"

    def _send_sse_start(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

    def _send_sse_event(self, data: dict) -> bool:
        """Write one SSE event. Returns False if the client disconnected."""
        encoded = json.dumps(data, ensure_ascii=False)
        event_bytes = f"data: {encoded}\n\n".encode("utf-8")
        try:
            self.wfile.write(event_bytes)
            self.wfile.flush()
            return True
        except (BrokenPipeError, ConnectionResetError, OSError):
            return False

    def _send_json(self, payload: dict | list, status: int = 200) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/health":
            self._send_json({"status": "ok"})
            return
        if path == "/api/ui-state":
            self._send_json(SERVICE.get_ui_state())
            return
        if path == "/api/visualizer-payload":
            document_id = (query.get("document_id") or [""])[0]
            if not document_id:
                self._send_json({}, status=200)
                return
            self._send_json(SERVICE.get_visualizer_payload(document_id=document_id))
            return
        if path == "/api/backend-job-status":
            job_id = (query.get("job_id") or [""])[0]
            if not job_id:
                self._send_json({"error": "job_id is required"}, status=400)
                return
            self._send_json(SERVICE.get_backend_job_status(job_id=job_id))
            return
        if path == "/api/document-artifacts":
            document_id = (query.get("document_id") or [""])[0]
            if not document_id:
                self._send_json([], status=200)
                return
            self._send_json(SERVICE.list_document_artifacts(document_id=document_id))
            return
        if path == "/api/document-artifact-download":
            document_id = (query.get("document_id") or [""])[0]
            name = (query.get("name") or [""])[0]
            if not document_id or not name:
                self._send_json({"error": "document_id and name are required"}, status=400)
                return
            base = Path(os.getenv("MEDIA_CONTRACT_ARTIFACTS_DIR", "artifacts/media_contracts")).resolve()
            candidate = (base / document_id / name).resolve()
            if not str(candidate).startswith(str(base)) or not candidate.exists() or not candidate.is_file():
                self._send_json({"error": "Not found"}, status=404)
                return
            data = candidate.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Content-Disposition", f'attachment; filename="{candidate.name}"')
            self.end_headers()
            self.wfile.write(data)
            return
        self._send_json({"error": "Not found"}, status=404)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        content_type = self.headers.get("Content-Type", "")

        if path == "/api/upload":
            if "multipart/form-data" not in content_type:
                self._send_json({"error": "multipart/form-data is required"}, status=400)
                return
            storage = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={"REQUEST_METHOD": "POST", "CONTENT_TYPE": content_type},
            )
            upload_item = storage["file"] if "file" in storage else None
            if upload_item is None or not getattr(upload_item, "filename", None):
                self._send_json({"error": "file field is required"}, status=400)
                return
            base_dir = Path(os.getenv("MEDIA_TEMP_DIR", "artifacts/media_tmp")) / "uploads"
            base_dir.mkdir(parents=True, exist_ok=True)
            safe_name = Path(str(upload_item.filename)).name
            save_path = base_dir / safe_name
            data = upload_item.file.read()
            save_path.write_bytes(data)
            self._send_json({"fileName": safe_name, "mediaPath": str(save_path), "sizeBytes": len(data)})
            return

        if path == "/api/render-media":
            source_audio_bytes = b""
            if "multipart/form-data" in content_type:
                form = cgi.FieldStorage(
                    fp=self.rfile,
                    headers=self.headers,
                    environ={"REQUEST_METHOD": "POST", "CONTENT_TYPE": content_type},
                )
                meta_raw = form["meta"].value if "meta" in form else "{}"
                try:
                    body = json.loads(meta_raw)
                except json.JSONDecodeError:
                    body = {}
                if "audio" in form:
                    try:
                        source_audio_bytes = form["audio"].file.read()
                    except Exception:
                        source_audio_bytes = b""
            else:
                body = self._read_json_body()
            sentences = body.get("sentences") or []
            voice = str(body.get("voice") or "male").strip().lower()
            subtitles_mode = str(body.get("subtitlesMode") or "bilingual").strip()
            need_audio = bool(body.get("need_audio", True))
            need_video = bool(body.get("need_video", True))
            if not sentences:
                self._send_json({"error": "sentences is required"}, status=400)
                return
            try:
                zip_bytes = _render_media_artifacts(sentences, voice, subtitles_mode, need_audio=need_audio, need_video=need_video, source_audio_bytes=source_audio_bytes)
                self.send_response(200)
                self.send_header("Content-Type", "application/zip")
                self.send_header("Content-Length", str(len(zip_bytes)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(zip_bytes)
            except Exception as exc:
                import traceback as _tb
                _tb.print_exc()
                self._send_json({"error": str(exc)}, status=500)
            return

        body = self._read_json_body()
        if path == "/api/submit-media":
            media_path = str(body.get("mediaPath") or body.get("media_path") or "").strip()
            duration = _env_int("ELA_DEFAULT_DURATION_SEC", 1) if body.get("durationSec") is None else int(body.get("durationSec") or 0)
            size = _env_int("ELA_DEFAULT_SIZE_BYTES", 0) if body.get("sizeBytes") is None else int(body.get("sizeBytes") or 0)
            if not media_path:
                self._send_json({"error": "mediaPath is required"}, status=400)
                return
            if duration <= 0:
                duration = 1
            try:
                payload = SERVICE.submit_media(
                    media_path=media_path,
                    duration_seconds=duration,
                    size_bytes=size,
                    project_id=body.get("projectId"),
                    media_file_id=body.get("mediaFileId"),
                    translation_provider=body.get("translationProvider"),
                    subtitles_mode=body.get("subtitlesMode"),
                    voice_choice=body.get("voiceChoice"),
                    force_full_reprocess=bool(body.get("forceFullReprocess")),
                    async_local_processing=True,
                )
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=400)
                return
            self._send_json(payload)
            return
        if path == "/api/cancel-job":
            job_id = str(body.get("job_id") or body.get("jobId") or "").strip()
            if not job_id:
                self._send_json({"error": "job_id is required"}, status=400)
                return
            payload = SERVICE.cancel_backend_job(job_id=job_id)
            self._send_json(payload, status=200 if payload.get("status") == "ok" else 404)
            return
        if path == "/api/delete-analysis":
            document_id = str(body.get("document_id") or body.get("documentId") or "").strip()
            if not document_id:
                self._send_json({"error": "document_id is required"}, status=400)
                return
            payload = SERVICE.delete_analysis(document_id=document_id)
            self._send_json(payload, status=200 if payload.get("status") == "ok" else 404)
            return
        if path == "/api/transcribe":
            media_path = str(body.get("mediaPath") or body.get("media_path") or "").strip()
            if not media_path:
                self._send_json({"error": "mediaPath is required"}, status=400)
                return
            evt_queue: "_queue.Queue[dict]" = _queue.Queue()

            def _transcribe_worker() -> None:
                try:
                    result = extract_media_text_and_sentences(source_path=media_path)
                    sentences = [
                        {
                            "text": text,
                            "start_sec": timing["start_sec"] if timing else None,
                            "end_sec": timing["end_sec"] if timing else None,
                        }
                        for text, timing in zip(result.sentence_stream, result.sentence_timeline)
                    ]
                    evt_queue.put({
                        "status": "done",
                        "source_type": result.source_type,
                        "full_text": result.full_text,
                        "sentences": sentences,
                    })
                except FileNotFoundError as exc:
                    evt_queue.put({"status": "error", "error": str(exc)})
                except Exception as exc:
                    evt_queue.put({"status": "error", "error": str(exc)})

            _threading.Thread(target=_transcribe_worker, daemon=True).start()
            self._send_sse_start()
            while True:
                try:
                    event = evt_queue.get(timeout=20)
                    if not self._send_sse_event(event):
                        break
                    if event.get("status") in ("done", "error"):
                        break
                except _queue.Empty:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
            return

        if path == "/api/tts-batch":
            import uuid as _uuid
            sentences = body.get("sentences") or []
            if not isinstance(sentences, list):
                self._send_json({"error": "sentences must be an array"}, status=400)
                return
            document_id = str(body.get("documentId") or body.get("document_id") or "").strip()
            if not document_id:
                document_id = str(_uuid.uuid4())
            source_type = str(body.get("sourceType") or body.get("source_type") or "audio").strip().lower()
            source_path = str(body.get("mediaPath") or body.get("media_path") or "").strip()
            voice_choice = str(body.get("voiceChoice") or body.get("voice_choice") or "male").strip()
            subtitles_mode = str(body.get("subtitlesMode") or body.get("subtitles_mode") or "bilingual").strip()
            base = Path(os.getenv("MEDIA_CONTRACT_ARTIFACTS_DIR", "artifacts/media_contracts")).resolve()
            doc_dir = base / document_id
            doc_dir.mkdir(parents=True, exist_ok=True)
            # Stream progress via SSE — one request, no polling, Cloudflare-safe.
            # TTS runs in a background thread; main thread drains the event queue
            # and sends ": keepalive" comments every 20 s so Cloudflare never sees
            # an idle connection (needed during long ffmpeg video-mux steps).
            evt_queue: "_queue.Queue[dict]" = _queue.Queue()

            def _worker() -> None:
                def _progress(stage: str, ratio: "float | None", msg: "str | None") -> None:
                    evt_queue.put({"status": "progress", "stage": stage, "ratio": ratio or 0, "message": msg or ""})
                try:
                    artifacts = SERVICE.generate_tts_batch(
                        sentences=sentences,
                        doc_dir=doc_dir,
                        source_type=source_type,
                        source_path=source_path,
                        voice_choice=voice_choice,
                        subtitles_mode=subtitles_mode,
                        stage_callback=_progress,
                    )
                    artifact_list = [
                        {
                            "name": a["name"],
                            "size_bytes": a["size_bytes"],
                            "download_url": f"/api/document-artifact-download?document_id={document_id}&name={a['name']}",
                        }
                        for a in artifacts
                    ]
                    evt_queue.put({"status": "done", "document_id": document_id, "artifacts": artifact_list})
                except Exception as exc:
                    evt_queue.put({"status": "error", "error": str(exc)})

            _threading.Thread(target=_worker, daemon=True).start()
            self._send_sse_start()
            while True:
                try:
                    event = evt_queue.get(timeout=20)
                    if not self._send_sse_event(event):
                        break  # client disconnected
                    if event.get("status") in ("done", "error"):
                        break
                except _queue.Empty:
                    # No progress for 20 s (e.g. ffmpeg muxing) — send SSE comment
                    # to keep the Cloudflare connection alive.
                    try:
                        self.wfile.write(b": keepalive\n\n")
                        self.wfile.flush()
                    except OSError:
                        break
            return

        if path == "/api/tts-sentence":
            import asyncio as _asyncio
            import tempfile as _tempfile
            text = str(body.get("text") or "").strip()
            voice_choice = str(body.get("voiceChoice") or body.get("voice_choice") or "male").strip().lower()
            if not text:
                self._send_json({"error": "text is required"}, status=400)
                return
            voice_name = "ru-RU-SvetlanaNeural" if voice_choice.startswith("f") else "ru-RU-DmitryNeural"
            try:
                import edge_tts as _edge_tts  # type: ignore
                with _tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as _f:
                    _tmp_path = _f.name
                _asyncio.run(_edge_tts.Communicate(text, voice_name).save(_tmp_path))
                _data = Path(_tmp_path).read_bytes()
                try:
                    Path(_tmp_path).unlink()
                except OSError:
                    pass
                self.send_response(200)
                self.send_header("Content-Type", "audio/mpeg")
                self.send_header("Content-Length", str(len(_data)))
                self.end_headers()
                self.wfile.write(_data)
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=500)
            return

        if path == "/api/sentence-contract":
            sentence_text = str(body.get("sentenceText") or body.get("sentence_text") or "").strip()
            if not sentence_text:
                self._send_json({"error": "sentenceText is required"}, status=400)
                return
            sentence_idx_raw = body.get("sentenceIdx", body.get("sentence_idx", 0))
            try:
                sentence_idx = int(sentence_idx_raw)
            except (TypeError, ValueError):
                self._send_json({"error": "sentenceIdx must be an integer"}, status=400)
                return
            try:
                payload = _build_sentence_contract_payload(sentence_text, sentence_idx)
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=400)
                return
            self._send_json(payload)
            return

        self._send_json({"error": "Not found"}, status=404)


def main() -> None:
    import threading

    host = os.getenv("ELA_RUNTIME_HTTP_HOST", "0.0.0.0")
    port = _env_int("ELA_RUNTIME_HTTP_PORT", 8000)
    server = ThreadingHTTPServer((host, port), RuntimeApiHandler)
    print(f"[runtime-api] serving on http://{host}:{port}", flush=True)

    # Run warmup in a background thread so the server starts accepting connections
    # immediately.  Without this, the 2-3 minute warmup window leaves the port
    # closed and Cloudflare / nginx return 502 "Bad Gateway" for any request that
    # arrives during that window.
    def _warmup():
        _run_sentence_contract_warmup()
        _run_media_pipeline_warmup()

    threading.Thread(target=_warmup, daemon=True).start()
    server.serve_forever()


if __name__ == "__main__":
    main()
