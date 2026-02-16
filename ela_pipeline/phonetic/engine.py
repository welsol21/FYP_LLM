"""Phonetic transcription engines (UK/US) for English text."""

from __future__ import annotations

import shutil
import subprocess
from typing import Protocol


class PhoneticTranscriber(Protocol):
    def transcribe_text(self, text: str, accent: str) -> str:
        ...


class EspeakPhoneticTranscriber:
    """Wrapper over espeak-ng/espeak IPA output for EN-UK / EN-US."""

    _VOICE_BY_ACCENT = {
        "uk": "en-gb",
        "us": "en-us",
    }

    def __init__(self, binary: str = "auto") -> None:
        self.binary = self._resolve_binary(binary)

    @staticmethod
    def _resolve_binary(binary: str) -> str:
        b = (binary or "auto").strip().lower()
        if b in {"espeak", "espeak-ng"}:
            path = shutil.which(b)
            if path is None:
                raise FileNotFoundError(f"phonetic binary not found: {b}")
            return path
        if b == "auto":
            for candidate in ("espeak-ng", "espeak"):
                path = shutil.which(candidate)
                if path is not None:
                    return path
            raise FileNotFoundError("phonetic binary not found: expected espeak-ng or espeak in PATH")
        raise ValueError("phonetic_binary must be one of: auto | espeak | espeak-ng")

    @staticmethod
    def _normalize_ipa(text: str) -> str:
        # espeak may emit separators and extra whitespace for multi-word spans.
        return " ".join(text.replace("_", " ").strip().split())

    def transcribe_text(self, text: str, accent: str) -> str:
        raw = (text or "").strip()
        if not raw:
            return ""
        acc = (accent or "").strip().lower()
        voice = self._VOICE_BY_ACCENT.get(acc)
        if voice is None:
            raise ValueError("accent must be one of: uk | us")
        cmd = [self.binary, "-q", "--ipa=3", "-v", voice, raw]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return self._normalize_ipa(proc.stdout)
