"""T5 renderer that rewrites a note from a signature-only prompt."""

from __future__ import annotations

import os

import torch
from transformers import T5ForConditionalGeneration, T5Tokenizer

from ela_pipeline.annotate.signature_note_prompt import build_signature_note_training_prompt
from ela_pipeline.validation.notes_quality import sanitize_note


class SignatureOnlyT5NoteRenderer:
    def __init__(
        self,
        model_dir: str,
        *,
        max_input_length: int = 512,
        max_target_length: int = 128,
        device: str = "auto",
    ) -> None:
        if not os.path.isdir(model_dir):
            raise FileNotFoundError(f"Model directory not found: {model_dir}")
        requested = str(device or "auto").strip().lower()
        if requested not in {"auto", "cpu", "cuda"}:
            raise ValueError("device must be one of: auto | cpu | cuda")
        if requested == "cuda":
            if not torch.cuda.is_available():
                raise RuntimeError("CUDA requested for signature-only T5 renderer but not available.")
            resolved_device = "cuda"
        elif requested == "cpu":
            resolved_device = "cpu"
        else:
            resolved_device = "cuda" if torch.cuda.is_available() else "cpu"

        self.device = torch.device(resolved_device)
        self.max_input_length = max_input_length
        self.max_target_length = max_target_length
        self.tokenizer = T5Tokenizer.from_pretrained(model_dir)
        self.model = T5ForConditionalGeneration.from_pretrained(model_dir).to(self.device)
        self.model.eval()

    def render_note(
        self,
        *,
        signature_text: str,
        level: str,
        node_level: str = "Sentence",
        depth: int = 2,
        family_id: str = "",
    ) -> str:
        prompt = build_signature_note_training_prompt(
            signature_text=signature_text,
            node_level=node_level,
            audience_level=level,
            depth=depth,
            family_id=family_id,
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
        return note
