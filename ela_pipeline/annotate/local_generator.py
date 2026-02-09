"""Local T5 generator for linguistic notes."""

from __future__ import annotations

import os
from typing import Dict, List

import torch
from transformers import T5ForConditionalGeneration, T5Tokenizer

from ela_pipeline.validation.notes_quality import is_valid_note, sanitize_note


class LocalT5Annotator:
    def __init__(
        self,
        model_dir: str,
        max_input_length: int = 512,
        max_target_length: int = 128,
        max_retries: int = 2,
    ):
        if not os.path.isdir(model_dir):
            raise FileNotFoundError(
                f"Model directory not found: {model_dir}. "
                "Run training first or pass an existing local model directory."
            )

        self.device = torch.device("cpu")
        self.max_input_length = max_input_length
        self.max_target_length = max_target_length
        self.max_retries = max_retries

        self.tokenizer = T5Tokenizer.from_pretrained(model_dir)
        self.model = T5ForConditionalGeneration.from_pretrained(model_dir).to(self.device)
        self.model.eval()

    def _build_prompt(self, sentence: str, node: Dict) -> str:
        return (
            "Write one short educational linguistic note in natural English. "
            "Do not output field names, labels, placeholders, booleans, or JSON fragments. "
            f"Sentence: {sentence} "
            f"Node type: {node['type']}. "
            f"Part of speech: {node['part_of_speech']}. "
            f"Tense: {node['tense']}. "
            f"Node content: {node['content']}"
        )

    def _generate(self, prompt: str, *, do_sample: bool, temperature: float) -> str:
        enc = self.tokenizer(
            prompt,
            return_tensors="pt",
            truncation=True,
            max_length=self.max_input_length,
        )
        enc = {k: v.to(self.device) for k, v in enc.items()}

        generation_kwargs = {
            "max_length": self.max_target_length,
            "num_beams": 1,
            "do_sample": do_sample,
        }
        if do_sample:
            generation_kwargs["temperature"] = temperature
            generation_kwargs["top_p"] = 0.9

        with torch.no_grad():
            out = self.model.generate(**enc, **generation_kwargs)
        return self.tokenizer.decode(out[0], skip_special_tokens=True).strip()

    def _generate_note_with_retry(self, prompt: str) -> str:
        candidates: List[str] = []
        attempts = max(1, self.max_retries + 1)

        for attempt in range(attempts):
            do_sample = attempt > 0
            temperature = 0.8 + (0.1 * attempt)
            note = sanitize_note(self._generate(prompt, do_sample=do_sample, temperature=temperature))
            candidates.append(note)
            if is_valid_note(note):
                return note

        for note in candidates:
            if note:
                return note
        return ""

    def annotate(self, contract_doc: Dict[str, Dict]) -> Dict[str, Dict]:
        for sentence_text, sentence_node in contract_doc.items():
            self._annotate_node(sentence_text, sentence_node)
        return contract_doc

    def _annotate_node(self, sentence_text: str, node: Dict) -> None:
        prompt = self._build_prompt(sentence_text, node)
        note = self._generate_note_with_retry(prompt)
        node["linguistic_notes"] = [note] if is_valid_note(note) else []

        for child in node.get("linguistic_elements", []):
            self._annotate_node(sentence_text, child)
