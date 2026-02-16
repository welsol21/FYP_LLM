"""Multilingual translation engines for pipeline enrichment."""

from __future__ import annotations

from typing import Protocol

import torch
from transformers import M2M100ForConditionalGeneration, M2M100Tokenizer


class Translator(Protocol):
    def translate_text(self, text: str, source_lang: str, target_lang: str) -> str:
        ...


class M2M100Translator:
    """Thin wrapper over facebook/m2m100_418M for sentence/node translation."""

    def __init__(
        self,
        model_name: str = "facebook/m2m100_418M",
        device: str = "auto",
        max_target_length: int = 256,
    ) -> None:
        self.model_name = model_name
        self.max_target_length = max_target_length
        self.device = self._resolve_device(device)

        self.tokenizer = M2M100Tokenizer.from_pretrained(model_name)
        self.model = M2M100ForConditionalGeneration.from_pretrained(model_name).to(self.device)
        self.model.eval()

    @staticmethod
    def _resolve_device(device: str) -> str:
        dev = (device or "auto").strip().lower()
        if dev == "auto":
            return "cuda" if torch.cuda.is_available() else "cpu"
        if dev in {"cpu", "cuda"}:
            if dev == "cuda" and not torch.cuda.is_available():
                return "cpu"
            return dev
        raise ValueError("translation_device must be one of: auto | cpu | cuda")

    def translate_text(self, text: str, source_lang: str, target_lang: str) -> str:
        raw = (text or "").strip()
        if not raw:
            return ""

        src = (source_lang or "").strip()
        tgt = (target_lang or "").strip()
        if not src or not tgt:
            raise ValueError("source_lang and target_lang must be non-empty")

        self.tokenizer.src_lang = src
        encoded = self.tokenizer(
            raw,
            return_tensors="pt",
            truncation=True,
            max_length=512,
        ).to(self.device)

        forced_bos_token_id = self.tokenizer.get_lang_id(tgt)
        with torch.no_grad():
            generated = self.model.generate(
                **encoded,
                forced_bos_token_id=forced_bos_token_id,
                max_length=self.max_target_length,
            )
        return self.tokenizer.batch_decode(generated, skip_special_tokens=True)[0].strip()
