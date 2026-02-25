"""Controlled T5 renderer for classifier note blueprints."""

from __future__ import annotations

import os

import torch
from transformers import T5ForConditionalGeneration, T5Tokenizer

from ela_pipeline.validation.notes_quality import sanitize_note


class ControlledT5NoteRenderer:
    """Rewrite blueprint notes into user-facing text while keeping classifier truth fields immutable."""

    def __init__(
        self,
        model_dir: str,
        *,
        max_input_length: int = 512,
        max_target_length: int = 128,
    ) -> None:
        if not os.path.isdir(model_dir):
            raise FileNotFoundError(f"Model directory not found: {model_dir}")
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is required for controlled T5 note rendering.")

        self.device = torch.device("cuda")
        self.max_input_length = max_input_length
        self.max_target_length = max_target_length
        self.tokenizer = T5Tokenizer.from_pretrained(model_dir)
        self.model = T5ForConditionalGeneration.from_pretrained(model_dir).to(self.device)
        self.model.eval()

    def _build_prompt(
        self,
        *,
        blueprint_text: str,
        level: str,
        sentence_text: str,
        node_text: str,
        node_type: str,
        part_of_speech: str,
        cefr_level: str,
    ) -> str:
        return (
            "Rewrite this linguistic note blueprint into one short educational note in natural English. "
            "Keep grammar meaning precise. Do not add JSON, labels, or extra fields. "
            f"Level: {level}. CEFR: {cefr_level}. Node type: {node_type}. Part of speech: {part_of_speech}. "
            f"Sentence: {sentence_text} Node: {node_text} Blueprint: {blueprint_text}"
        )

    def render_note(
        self,
        *,
        blueprint_text: str,
        level: str,
        sentence_text: str,
        node_text: str,
        node_type: str,
        part_of_speech: str,
        cefr_level: str,
    ) -> str:
        prompt = self._build_prompt(
            blueprint_text=blueprint_text,
            level=level,
            sentence_text=sentence_text,
            node_text=node_text,
            node_type=node_type,
            part_of_speech=part_of_speech,
            cefr_level=cefr_level,
        )
        enc = self.tokenizer(
            prompt,
            return_tensors="pt",
            truncation=True,
            max_length=self.max_input_length,
        )
        enc = {k: v.to(self.device) for k, v in enc.items()}
        with torch.no_grad():
            out = self.model.generate(
                **enc,
                max_length=self.max_target_length,
                num_beams=4,
                do_sample=False,
            )
        note = sanitize_note(self.tokenizer.decode(out[0], skip_special_tokens=True))
        if not note:
            return str(blueprint_text or "").strip()
        return note

