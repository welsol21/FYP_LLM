"""Local T5 generator for linguistic notes."""

from __future__ import annotations

import os
from typing import Dict

import torch
from transformers import T5ForConditionalGeneration, T5Tokenizer


class LocalT5Annotator:
    def __init__(self, model_dir: str, max_input_length: int = 512, max_target_length: int = 128):
        if not os.path.isdir(model_dir):
            raise FileNotFoundError(
                f"Model directory not found: {model_dir}. "
                "Run training first or pass an existing local model directory."
            )

        self.device = torch.device("cpu")
        self.max_input_length = max_input_length
        self.max_target_length = max_target_length

        self.tokenizer = T5Tokenizer.from_pretrained(model_dir)
        self.model = T5ForConditionalGeneration.from_pretrained(model_dir).to(self.device)
        self.model.eval()

    def _build_prompt(self, sentence: str, node: Dict) -> str:
        return (
            f"sentence: {sentence} "
            f"node_type: {node['type']} "
            f"part_of_speech: {node['part_of_speech']} "
            f"tense: {node['tense']} "
            f"content: {node['content']}"
        )

    def _generate(self, prompt: str) -> str:
        enc = self.tokenizer(
            prompt,
            return_tensors="pt",
            truncation=True,
            max_length=self.max_input_length,
        )
        enc = {k: v.to(self.device) for k, v in enc.items()}

        with torch.no_grad():
            out = self.model.generate(**enc, max_length=self.max_target_length, num_beams=1)
        return self.tokenizer.decode(out[0], skip_special_tokens=True).strip()

    def annotate(self, contract_doc: Dict[str, Dict]) -> Dict[str, Dict]:
        for sentence_text, sentence_node in contract_doc.items():
            self._annotate_node(sentence_text, sentence_node)
        return contract_doc

    def _annotate_node(self, sentence_text: str, node: Dict) -> None:
        prompt = self._build_prompt(sentence_text, node)
        note = self._generate(prompt)
        node["linguistic_notes"] = [note] if note else []

        for child in node.get("linguistic_elements", []):
            self._annotate_node(sentence_text, child)
