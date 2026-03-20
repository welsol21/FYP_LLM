"""Controlled T5 renderer for classifier note blueprints."""

from __future__ import annotations

import json
import os

import torch
from transformers import T5ForConditionalGeneration, T5Tokenizer

from ela_pipeline.annotate.note_context import build_note_context_prompt
from ela_pipeline.validation.notes_quality import sanitize_note


class ControlledT5NoteRenderer:
    """Rewrite blueprint notes into user-facing text while keeping classifier truth fields immutable."""

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
                raise RuntimeError("CUDA requested for controlled T5 renderer but not available.")
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

    def _build_prompt(
        self,
        *,
        template_payload: dict | None,
        deterministic_note: str,
        blueprint_text: str,
        level: str,
        node: dict,
        parent: dict | None,
        sentence_node: dict,
        path_types: list[str],
        depth: int,
        sibling_index: int,
        sibling_count: int,
    ) -> str:
        if isinstance(template_payload, dict):
            template_brief = {
                "note_template_version": template_payload.get("note_template_version"),
                "template_id": template_payload.get("template_id"),
                "template_text": template_payload.get("template_text"),
                "allowed_slots": template_payload.get("allowed_slots"),
                "slot_values": template_payload.get("slot_values"),
                "selection": template_payload.get("selection"),
                "deterministic_note": deterministic_note,
                "context": template_payload.get("note_template_input"),
            }
            return (
                "Rewrite this contract-safe linguistic note into one short educational note in natural English. "
                "Keep all structural facts from the template and slot values. "
                "Do not invent placeholders, new structure, JSON, labels, or extra fields. "
                f"Audience level: {level}. "
                f"Payload: {json.dumps(template_brief, ensure_ascii=False, sort_keys=True)}"
            )
        context = build_note_context_prompt(
            node=node,
            parent=parent,
            sentence_node=sentence_node,
            path_types=path_types,
            depth=depth,
            sibling_index=sibling_index,
            sibling_count=sibling_count,
            template_version="v2_flat_context",
        )
        return (
            "Rewrite this linguistic note blueprint into one short educational note in natural English. "
            "Keep grammar meaning precise. Use only grammatical context from the payload. "
            "Do not add JSON, labels, or extra fields. "
            f"Audience level: {level}. "
            f"Blueprint: {blueprint_text}. "
            f"Context: {context}"
        )

    def render_note(
        self,
        *,
        blueprint_text: str = "",
        level: str,
        node: dict,
        parent: dict | None,
        sentence_node: dict,
        path_types: list[str],
        depth: int,
        sibling_index: int,
        sibling_count: int,
        template_payload: dict | None = None,
        deterministic_note: str = "",
    ) -> str:
        prompt = self._build_prompt(
            template_payload=template_payload,
            deterministic_note=deterministic_note,
            blueprint_text=blueprint_text,
            level=level,
            node=node,
            parent=parent,
            sentence_node=sentence_node,
            path_types=path_types,
            depth=depth,
            sibling_index=sibling_index,
            sibling_count=sibling_count,
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
            if deterministic_note:
                return str(deterministic_note or "").strip()
            return str(blueprint_text or "").strip()
        return note
