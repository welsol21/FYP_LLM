"""Local T5 generator for linguistic notes."""

from __future__ import annotations

import os
import re
from typing import Dict, List, Set

import torch
from transformers import T5ForConditionalGeneration, T5Tokenizer

from ela_pipeline.annotate.fallback_notes import build_fallback_note
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

    def _generate_note_with_retry(self, prompt: str) -> tuple[str, List[str]]:
        candidates: List[str] = []
        rejected: List[str] = []
        attempts = max(1, self.max_retries + 1)

        for attempt in range(attempts):
            do_sample = attempt > 0
            temperature = 0.8 + (0.1 * attempt)
            note = sanitize_note(self._generate(prompt, do_sample=do_sample, temperature=temperature))
            candidates.append(note)
            if is_valid_note(note):
                return note, rejected
            if note:
                rejected.append(note)

        for note in candidates:
            if note:
                return note, rejected
        return "", rejected

    def _is_note_suitable_for_node(self, node: Dict, note: str) -> bool:
        if not is_valid_note(note):
            return False

        node_type = (node.get("type") or "").strip()
        content = sanitize_note(str(node.get("content", ""))).lower()
        note_l = sanitize_note(note).lower()

        if node_type == "Word":
            # Force strict lexical anchoring in quoted form to suppress generic noise.
            if content and f"'{content}'" not in note_l:
                return False
            return True

        if node_type == "Phrase":
            if "phrase" not in note_l:
                return False
            phrase_tokens = [t for t in re.findall(r"[a-z]+", content) if len(t) >= 4]
            if phrase_tokens and not any(tok in note_l for tok in phrase_tokens[:2]):
                return False
            return True

        if node_type == "Sentence":
            if "sentence" not in note_l:
                return False
            tense = (node.get("tense") or "").lower()
            if tense == "past" and "present simple" in note_l:
                return False
            if tense == "present" and "past simple" in note_l:
                return False
            return True

        return True

    def _infer_note_kind(self, node: Dict, note: str) -> str:
        note_l = sanitize_note(note).lower()
        if any(marker in note_l for marker in ("tense", "aspect", "voice", "mood", "verb form", "plural", "singular")):
            return "morphological"
        if any(marker in note_l for marker in ("subject", "predicate", "object", "clause", "phrase", "sentence", "agreement")):
            return "syntactic"
        if any(marker in note_l for marker in ("topic", "context", "cohesion", "register", "emphasis")):
            return "discourse"
        return "semantic"

    def _build_typed_note(self, node: Dict, note: str, source: str) -> Dict[str, object]:
        return {
            "text": note,
            "kind": self._infer_note_kind(node, note),
            "confidence": 0.85 if source == "model" else 0.65,
            "source": source,
        }

    def annotate(self, contract_doc: Dict[str, Dict]) -> Dict[str, Dict]:
        for sentence_text, sentence_node in contract_doc.items():
            seen_notes: Set[str] = set()
            self._annotate_node(sentence_text, sentence_node, seen_notes)
        return contract_doc

    def _annotate_node(self, sentence_text: str, node: Dict, seen_notes: Set[str]) -> None:
        prompt = self._build_prompt(sentence_text, node)
        note, rejected_candidates = self._generate_note_with_retry(prompt)
        norm_note = sanitize_note(note).lower()
        node_type = (node.get("type") or "").strip()
        should_dedupe = node_type != "Word"
        note_is_valid = is_valid_note(note)
        note_is_suitable = self._is_note_suitable_for_node(node, note)
        is_new_note = (norm_note not in seen_notes) if should_dedupe else True

        node["quality_flags"] = []
        node["rejected_candidates"] = list(rejected_candidates)
        node["reason_codes"] = []

        if note_is_valid and note_is_suitable and is_new_note:
            node["linguistic_notes"] = [note]
            node["notes"] = [self._build_typed_note(node, note, source="model")]
            node["quality_flags"] = ["note_generated", "model_used"]
            node["reason_codes"] = ["MODEL_NOTE_ACCEPTED"]
            if should_dedupe:
                seen_notes.add(norm_note)
        else:
            if note and note not in node["rejected_candidates"]:
                node["rejected_candidates"].append(note)
            if not note_is_valid:
                node["reason_codes"].append("MODEL_OUTPUT_LOW_QUALITY")
            elif not note_is_suitable:
                node["reason_codes"].append("MODEL_NOTE_UNSUITABLE")
            elif not is_new_note:
                node["reason_codes"].append("DUPLICATE_NOTE")

            fallback_note = build_fallback_note(node)
            fallback_norm = sanitize_note(fallback_note).lower()
            fallback_is_new = (fallback_norm not in seen_notes) if should_dedupe else True
            if self._is_note_suitable_for_node(node, fallback_note) and fallback_is_new:
                node["linguistic_notes"] = [fallback_note]
                node["notes"] = [self._build_typed_note(node, fallback_note, source="fallback")]
                node["quality_flags"] = ["fallback_used"]
                node["reason_codes"].append("FALLBACK_NOTE_ACCEPTED")
                if should_dedupe:
                    seen_notes.add(fallback_norm)
            else:
                node["linguistic_notes"] = []
                node["notes"] = []
                node["quality_flags"] = ["no_note"]
                node["reason_codes"].append("NO_VALID_NOTE")

        for child in node.get("linguistic_elements", []):
            self._annotate_node(sentence_text, child, seen_notes)
