"""Local T5 generator for linguistic notes."""

from __future__ import annotations

import os
import re
from typing import Dict, List, Set

import torch
from transformers import T5ForConditionalGeneration, T5Tokenizer

from ela_pipeline.annotate.fallback_notes import build_fallback_note
from ela_pipeline.annotate.template_registry import (
    all_template_ids,
    is_template_semantically_compatible,
    render_template_note,
    select_template_candidates,
)
from ela_pipeline.annotate.rejected_candidates import (
    DEFAULT_REJECTED_CANDIDATE_FILTER_CONFIG,
    RejectedCandidateFilterConfig,
    fails_semantic_sanity,
    normalize_and_aggregate_rejected_candidates,
)
from ela_pipeline.validation.notes_quality import is_valid_note, sanitize_note


class LocalT5Annotator:
    _TAM_RELEVANT_POS = {"sentence", "verb phrase", "verb", "auxiliary verb"}

    def __init__(
        self,
        model_dir: str,
        note_mode: str = "template_only",
        backoff_debug_summary: bool = False,
        max_input_length: int = 512,
        max_target_length: int = 128,
        max_retries: int = 2,
        rejection_filter_config: RejectedCandidateFilterConfig = DEFAULT_REJECTED_CANDIDATE_FILTER_CONFIG,
    ):
        self.note_mode = (note_mode or "template_only").strip().lower()
        if self.note_mode not in {"template_only", "llm", "hybrid", "two_stage"}:
            raise ValueError("note_mode must be one of: template_only | llm | hybrid | two_stage")

        self.device = None
        self.backoff_debug_summary = bool(backoff_debug_summary)
        self.max_input_length = max_input_length
        self.max_target_length = max_target_length
        self.max_retries = max_retries
        self.rejection_filter_config = rejection_filter_config

        self.tokenizer = None
        self.model = None
        self._template_ids = set(all_template_ids())
        if self.note_mode in {"llm", "hybrid", "two_stage"}:
            if not os.path.isdir(model_dir):
                raise FileNotFoundError(
                    f"Model directory not found: {model_dir}. "
                    "Run training first or pass an existing local model directory."
                )
            if not torch.cuda.is_available():
                raise RuntimeError(
                    "CUDA is required for inference with LocalT5Annotator in llm/hybrid/two_stage mode, but no GPU is available. "
                    "Run inference on a machine/session with visible NVIDIA GPU and CUDA-enabled PyTorch."
                )
            self.device = torch.device("cuda")
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

    def _build_template_id_prompt(self, sentence: str, node: Dict) -> str:
        return (
            "Predict exactly one template_id for this linguistic node. "
            "Output only the template_id token and nothing else. "
            f"Sentence: {sentence} "
            f"Node type: {node.get('type')} "
            f"Part of speech: {node.get('part_of_speech')} "
            f"Dependency: {node.get('dep_label') or node.get('grammatical_role')} "
            f"Tense: {node.get('tense')} "
            f"Aspect: {node.get('aspect')} "
            f"Mood: {node.get('mood')} "
            f"Node content: {node.get('content')}"
        )

    def _extract_template_id(self, raw: str) -> str:
        text = sanitize_note(raw).strip()
        if not text:
            return ""
        first = text.split("|", 1)[0].strip().upper()
        if first in self._template_ids:
            return first
        whole = text.upper()
        if whole in self._template_ids:
            return whole
        for token in re.findall(r"[A-Z_]{4,}", whole):
            if token in self._template_ids:
                return token
        return ""

    def _generate_template_note(self, node: Dict) -> tuple[str, str, Dict[str, object]]:
        candidates = select_template_candidates(node)
        rejected_semantic = []
        for selection in candidates:
            template_id = (selection.template_id or "").strip()
            if not template_id:
                continue
            if not is_template_semantically_compatible(node, template_id):
                rejected_semantic.append({"template_id": template_id, "level": selection.level})
                continue
            note = render_template_note(template_id, node, selection.matched_key or "")
            trace = self._trace_from_selection(
                selection,
                selection_mode=self._selection_mode_for_rule(selection),
                node=node,
            )
            if rejected_semantic:
                trace["semantic_rejects"] = rejected_semantic
            return template_id, sanitize_note(note), trace
        fallback = candidates[-1]
        trace = self._trace_from_selection(
            fallback,
            selection_mode=self._selection_mode_for_rule(fallback),
            node=node,
        )
        trace["template_id"] = None
        trace["semantic_rejects"] = rejected_semantic
        return "", "", trace

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

    def _generate_note_with_retry(self, prompt: str) -> tuple[str, List[Dict[str, str]]]:
        candidates: List[str] = []
        rejected: List[Dict[str, str]] = []
        attempts = max(1, self.max_retries + 1)

        for attempt in range(attempts):
            do_sample = attempt > 0
            temperature = 0.8 + (0.1 * attempt)
            note = sanitize_note(self._generate(prompt, do_sample=do_sample, temperature=temperature))
            candidates.append(note)
            if is_valid_note(note):
                return note, rejected
            if note:
                rejected.append({"text": note, "reason": "MODEL_OUTPUT_LOW_QUALITY"})

        for note in candidates:
            if note:
                return note, rejected
        return "", rejected

    def _predict_template_id_with_retry(self, prompt: str) -> tuple[str, List[Dict[str, str]]]:
        rejected: List[Dict[str, str]] = []
        attempts = max(1, self.max_retries + 1)
        seen_tokens: Set[str] = set()
        for attempt in range(attempts):
            do_sample = attempt > 0
            temperature = 0.7 + (0.1 * attempt)
            raw = self._generate(prompt, do_sample=do_sample, temperature=temperature)
            template_id = self._extract_template_id(raw)
            if template_id:
                return template_id, rejected
            # Keep only template-like tokens in rejection diagnostics; drop free-form model text noise.
            token = sanitize_note(raw).strip().upper()
            if token and re.fullmatch(r"[A-Z_]{4,}", token) and token not in seen_tokens:
                seen_tokens.add(token)
                rejected.append({"text": token, "reason": "MODEL_OUTPUT_LOW_QUALITY"})
        return "", rejected

    def _build_rejection_stats(self, node: Dict, rejected_items: List[Dict[str, str]]) -> tuple[List[str], List[Dict[str, object]]]:
        config = getattr(self, "rejection_filter_config", DEFAULT_REJECTED_CANDIDATE_FILTER_CONFIG)
        return normalize_and_aggregate_rejected_candidates(
            rejected_candidates=[],
            rejected_items=rejected_items,
            config=config,
            node_type=node.get("type"),
            node_part_of_speech=node.get("part_of_speech"),
            node_content=node.get("content"),
        )

    @staticmethod
    def _matched_context_key(selection) -> str | None:
        level = (selection.level or "").strip().upper()
        if level == "L1_EXACT":
            return selection.context_key_l1
        if level == "L2_DROP_TAM":
            return selection.context_key_l2
        if level.startswith("L3"):
            return selection.context_key_l3
        return selection.matched_key

    def _selection_mode_for_rule(self, selection) -> str:
        level = (selection.level or "").strip().upper()
        if level == "L1_EXACT":
            return "rule_l1_exact"
        if level == "L2_DROP_TAM":
            return "rule_l2_drop_tam"
        if level.startswith("L3"):
            return "rule_l3_backoff"
        return "rule_fallback"

    def _selection_mode_for_model(self, selection) -> str:
        level = (selection.level or "").strip().upper()
        if level == "L1_EXACT":
            return "model_l1_exact"
        if level == "L2_DROP_TAM":
            return "model_l2_drop_tam"
        if level.startswith("L3"):
            return "model_l3_backoff"
        return "model_predicted_template"

    def _is_tam_relevant_node(self, node: Dict) -> bool:
        node_pos = str(node.get("part_of_speech") or "").strip().lower()
        return node_pos in self._TAM_RELEVANT_POS

    def _trace_from_selection(self, selection, *, selection_mode: str, node: Dict | None = None) -> Dict[str, object]:
        trace = {
            "level": selection.level,
            "template_id": selection.template_id,
            "matched_key": selection.matched_key,
            "registry_version": selection.registry_version,
            "context_key_l1": selection.context_key_l1,
            "context_key_l2": selection.context_key_l2,
            "context_key_l3": selection.context_key_l3,
            "context_key_matched": self._matched_context_key(selection),
            "selection_mode": selection_mode,
        }
        if selection.level == "L2_DROP_TAM" and node and self._is_tam_relevant_node(node):
            trace["matched_level_reason"] = "tam_dropped"
        return trace

    def _match_selection_for_template_id(self, node: Dict, template_id: str) -> Dict[str, object]:
        candidates = select_template_candidates(node)
        for c in candidates:
            if (c.template_id or "").strip() == template_id:
                return self._trace_from_selection(
                    c,
                    selection_mode=self._selection_mode_for_model(c),
                    node=node,
                )
        fallback = candidates[-1]
        trace = self._trace_from_selection(
            fallback,
            selection_mode=self._selection_mode_for_model(fallback),
            node=node,
        )
        trace["level"] = "MODEL_PREDICTED"
        trace["template_id"] = template_id
        return trace

    def _is_note_suitable_for_node(self, node: Dict, note: str) -> bool:
        if not is_valid_note(note):
            return False

        node_type = (node.get("type") or "").strip()
        content = sanitize_note(str(node.get("content", ""))).lower()
        note_l = sanitize_note(note).lower()

        if fails_semantic_sanity(
            note_l,
            node_type=node.get("type"),
            node_part_of_speech=node.get("part_of_speech"),
            node_content=node.get("content"),
        ):
            return False

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

    @staticmethod
    def _normalize_tam_for_node(node: Dict) -> None:
        node_type = str(node.get("type", "")).strip().lower()
        pos = str(node.get("part_of_speech", "")).strip().lower()

        if node_type == "word":
            if pos not in {"verb", "auxiliary verb"}:
                for field in ("tense", "aspect", "mood", "voice", "finiteness"):
                    node[field] = None
            return

        if node_type == "phrase":
            if pos in {"noun phrase", "prepositional phrase"}:
                for field in ("tense", "aspect", "mood", "voice", "finiteness"):
                    node[field] = None
                return

            # For non-verbal phrases, mood/voice/finiteness are usually not meaningful.
            if pos not in {"verb phrase"}:
                for field in ("mood", "voice", "finiteness"):
                    node[field] = None

    @staticmethod
    def _kind_from_template_id(template_id: str) -> str | None:
        tid = (template_id or "").strip().upper()
        if not tid:
            return None
        if tid.startswith("WORD_"):
            return "morphological"
        if tid.startswith("SENTENCE_") or tid.startswith("CLAUSE_"):
            return "syntactic"
        if tid.startswith(("VP_", "NP_", "PP_", "PHRASE_")):
            return "syntactic"
        return None

    def _infer_note_kind(self, node: Dict, note: str, template_id: str | None = None) -> str:
        template_kind = self._kind_from_template_id(template_id or "")
        if template_kind:
            return template_kind
        note_l = sanitize_note(note).lower()
        if any(marker in note_l for marker in ("tense", "aspect", "voice", "mood", "verb form", "plural", "singular")):
            return "morphological"
        if any(marker in note_l for marker in ("subject", "predicate", "object", "clause", "phrase", "sentence", "agreement")):
            return "syntactic"
        if any(marker in note_l for marker in ("topic", "context", "cohesion", "register", "emphasis")):
            return "discourse"
        return "semantic"

    def _build_typed_note(self, node: Dict, note: str, source: str, template_id: str | None = None) -> Dict[str, object]:
        return {
            "text": note,
            "kind": self._infer_note_kind(node, note, template_id=template_id),
            "confidence": 0.85 if source == "model" else 0.65,
            "source": source,
        }

    @staticmethod
    def _with_backoff_flag(base_flags: List[str], template_trace: Dict[str, object] | None) -> List[str]:
        flags = list(base_flags)
        level = str((template_trace or {}).get("level") or "").upper()
        if level and level != "L1_EXACT" and "backoff_used" not in flags:
            flags.append("backoff_used")
        return flags

    def annotate(self, contract_doc: Dict[str, Dict]) -> Dict[str, Dict]:
        for sentence_text, sentence_node in contract_doc.items():
            seen_notes: Set[str] = set()
            self._annotate_node(sentence_text, sentence_node, seen_notes)
            self._mark_backoff_in_subtree(sentence_node)
            backoff_node_ids, backoff_leaf_node_ids, backoff_reasons, unique_spans = self._collect_backoff_summary(
                sentence_node
            )
            sentence_node["backoff_nodes_count"] = len(backoff_node_ids)
            sentence_node["backoff_leaf_nodes_count"] = len(backoff_leaf_node_ids)
            sentence_node["backoff_aggregate_nodes_count"] = max(
                0,
                sentence_node["backoff_nodes_count"] - sentence_node["backoff_leaf_nodes_count"],
            )
            sentence_node["backoff_unique_spans_count"] = len(unique_spans)
            if self.backoff_debug_summary:
                sentence_node["backoff_summary"] = {
                    "nodes": backoff_node_ids,
                    "leaf_nodes": backoff_leaf_node_ids,
                    "aggregate_nodes_count": sentence_node["backoff_aggregate_nodes_count"],
                    "unique_spans": unique_spans,
                    "reasons": backoff_reasons,
                }
            else:
                sentence_node.pop("backoff_summary", None)
        return contract_doc

    @staticmethod
    def _mark_backoff_in_subtree(node: Dict) -> bool:
        local_backoff = "backoff_used" in (node.get("quality_flags") or [])
        has_descendant_backoff = False

        for child in node.get("linguistic_elements", []) or []:
            if not isinstance(child, dict):
                continue
            if LocalT5Annotator._mark_backoff_in_subtree(child):
                has_descendant_backoff = True

        node["backoff_in_subtree"] = has_descendant_backoff
        return local_backoff or has_descendant_backoff

    @staticmethod
    def _collect_backoff_summary(node: Dict) -> tuple[List[str], List[str], List[str], List[str]]:
        node_ids: List[str] = []
        leaf_node_ids: List[str] = []
        reasons: Set[str] = set()
        unique_span_keys: Set[str] = set()

        def walk(cur: Dict) -> None:
            flags = cur.get("quality_flags") or []
            if isinstance(flags, list) and "backoff_used" in flags:
                node_id = cur.get("node_id")
                if isinstance(node_id, str):
                    node_ids.append(node_id)
                    if str(cur.get("type") or "").strip() != "Sentence":
                        leaf_node_ids.append(node_id)
                        span = cur.get("source_span")
                        if isinstance(span, dict):
                            start = span.get("start")
                            end = span.get("end")
                            if isinstance(start, int) and isinstance(end, int):
                                unique_span_keys.add(f"{start}:{end}")
                reason = str((cur.get("template_selection") or {}).get("matched_level_reason") or "").strip()
                if reason:
                    reasons.add(reason)
                else:
                    reasons.add("level_backoff")
            for child in cur.get("linguistic_elements", []) or []:
                if isinstance(child, dict):
                    walk(child)

        walk(node)
        return node_ids, leaf_node_ids, sorted(reasons), sorted(unique_span_keys)

    def _annotate_node(self, sentence_text: str, node: Dict, seen_notes: Set[str]) -> None:
        self._normalize_tam_for_node(node)
        node["quality_flags"] = []
        node["rejected_candidates"] = []
        node["rejected_candidate_stats"] = []
        node["reason_codes"] = []

        if self.note_mode == "two_stage":
            node_type = (node.get("type") or "").strip()
            should_dedupe = node_type != "Word"
            candidates = select_template_candidates(node)
            top = candidates[0] if candidates else None

            # Prefer exact deterministic mapping in production two-stage mode.
            if top and top.template_id and top.level in {"L1_EXACT", "L2_DROP_TAM"}:
                trace = self._trace_from_selection(
                    top,
                    selection_mode=self._selection_mode_for_rule(top),
                    node=node,
                )
                note = render_template_note(top.template_id, node, top.matched_key or "")
                note_norm = sanitize_note(note).lower()
                is_new = (note_norm not in seen_notes) if should_dedupe else True
                if note and self._is_note_suitable_for_node(node, note) and is_new:
                    node["linguistic_notes"] = [note]
                    node["notes"] = [self._build_typed_note(node, note, source="rule", template_id=top.template_id)]
                    node["quality_flags"] = self._with_backoff_flag(["template_selected", "rule_used"], trace)
                    node["reason_codes"] = ["RULE_TEMPLATE_ACCEPTED"]
                    node["template_selection"] = trace
                    if should_dedupe:
                        seen_notes.add(note_norm)
                else:
                    node["linguistic_notes"] = []
                    node["notes"] = []
                    node["quality_flags"] = ["no_note"]
                    node["reason_codes"] = ["NO_TEMPLATE_FOUND"]
                    node["template_selection"] = trace
                node["rejected_candidates"] = []
                node["rejected_candidate_stats"] = []
                for child in node.get("linguistic_elements", []):
                    self._annotate_node(sentence_text, child, seen_notes)
                return

            prompt = self._build_template_id_prompt(sentence_text, node)
            predicted_template_id, rejected_items = self._predict_template_id_with_retry(prompt)
            if predicted_template_id and is_template_semantically_compatible(node, predicted_template_id):
                selection = self._match_selection_for_template_id(node, predicted_template_id)
                note = render_template_note(predicted_template_id, node, str(selection.get("matched_key") or ""))
                note_norm = sanitize_note(note).lower()
                is_new = (note_norm not in seen_notes) if should_dedupe else True
                if note and self._is_note_suitable_for_node(node, note) and is_new:
                    node["linguistic_notes"] = [note]
                    node["notes"] = [self._build_typed_note(node, note, source="rule", template_id=predicted_template_id)]
                    node["quality_flags"] = self._with_backoff_flag(
                        ["model_predicted_template", "template_selected"],
                        selection,
                    )
                    node["reason_codes"] = ["MODEL_TEMPLATE_ACCEPTED"]
                    node["template_selection"] = selection
                    if should_dedupe:
                        seen_notes.add(note_norm)
                else:
                    node["linguistic_notes"] = []
                    node["notes"] = []
                    node["quality_flags"] = ["no_note"]
                    node["reason_codes"] = ["NO_TEMPLATE_FOUND"]
                    node["template_selection"] = selection
            else:
                fallback_template_id, fallback_note, fallback_trace = self._generate_template_note(node)
                fallback_norm = sanitize_note(fallback_note).lower()
                fallback_is_new = (fallback_norm not in seen_notes) if should_dedupe else True
                if fallback_note and fallback_is_new:
                    node["linguistic_notes"] = [fallback_note]
                    node["notes"] = [self._build_typed_note(node, fallback_note, source="rule", template_id=fallback_template_id)]
                    node["quality_flags"] = self._with_backoff_flag(["template_selected", "rule_used"], fallback_trace)
                    node["reason_codes"] = ["RULE_TEMPLATE_ACCEPTED"]
                    node["template_selection"] = fallback_trace
                    if should_dedupe:
                        seen_notes.add(fallback_norm)
                else:
                    node["linguistic_notes"] = []
                    node["notes"] = []
                    node["quality_flags"] = ["no_note"]
                    node["reason_codes"] = ["NO_TEMPLATE_FOUND"]
                    node["template_selection"] = fallback_trace

            deduped_rejected, rejected_stats = self._build_rejection_stats(node, rejected_items)
            node["rejected_candidates"] = deduped_rejected
            node["rejected_candidate_stats"] = rejected_stats
            for child in node.get("linguistic_elements", []):
                self._annotate_node(sentence_text, child, seen_notes)
            return

        # Stage A/B deterministic path: classify template_id -> render note.
        if self.note_mode in {"template_only", "hybrid"}:
            template_id, template_note, template_trace = self._generate_template_note(node)
            norm_template_note = sanitize_note(template_note).lower()
            node_type = (node.get("type") or "").strip()
            should_dedupe = node_type != "Word"
            template_is_new = (norm_template_note not in seen_notes) if should_dedupe else True
            if template_note and self._is_note_suitable_for_node(node, template_note) and template_is_new:
                node["linguistic_notes"] = [template_note]
                node["notes"] = [self._build_typed_note(node, template_note, source="rule", template_id=template_id)]
                node["quality_flags"] = self._with_backoff_flag(
                    ["note_generated", "rule_used", "template_selected"],
                    template_trace,
                )
                node["reason_codes"] = ["RULE_TEMPLATE_NOTE_ACCEPTED"]
                node["template_selection"] = template_trace
                if should_dedupe:
                    seen_notes.add(norm_template_note)
                for child in node.get("linguistic_elements", []):
                    self._annotate_node(sentence_text, child, seen_notes)
                return
            if self.note_mode == "template_only":
                fallback_note = build_fallback_note(node)
                fallback_norm = sanitize_note(fallback_note).lower()
                fallback_is_new = (fallback_norm not in seen_notes) if should_dedupe else True
                if self._is_note_suitable_for_node(node, fallback_note) and fallback_is_new:
                    node["linguistic_notes"] = [fallback_note]
                    node["notes"] = [self._build_typed_note(node, fallback_note, source="rule", template_id=None)]
                    node["quality_flags"] = ["note_generated", "rule_used", "template_fallback"]
                    node["reason_codes"] = ["RULE_TEMPLATE_MISS", "RULE_TEMPLATE_FALLBACK_ACCEPTED"]
                    node["template_selection"] = template_trace
                    if should_dedupe:
                        seen_notes.add(fallback_norm)
                else:
                    node["linguistic_notes"] = []
                    node["notes"] = []
                    node["quality_flags"] = ["no_note"]
                    node["reason_codes"] = ["RULE_TEMPLATE_MISS", "NO_VALID_NOTE"]
                    node["template_selection"] = template_trace
                for child in node.get("linguistic_elements", []):
                    self._annotate_node(sentence_text, child, seen_notes)
                return

        # LLM path (legacy) with retry + fallback.
        prompt = self._build_prompt(sentence_text, node)
        note, rejected_items = self._generate_note_with_retry(prompt)
        norm_note = sanitize_note(note).lower()
        node_type = (node.get("type") or "").strip()
        should_dedupe = node_type != "Word"
        note_is_valid = is_valid_note(note)
        note_is_suitable = self._is_note_suitable_for_node(node, note)
        is_new_note = (norm_note not in seen_notes) if should_dedupe else True

        if note_is_valid and note_is_suitable and is_new_note:
            node["linguistic_notes"] = [note]
            node["notes"] = [self._build_typed_note(node, note, source="model")]
            node["quality_flags"] = ["note_generated", "model_used"]
            node["reason_codes"] = ["MODEL_NOTE_ACCEPTED"]
            if should_dedupe:
                seen_notes.add(norm_note)
        else:
            if note:
                reject_reason = "MODEL_OUTPUT_LOW_QUALITY"
                if note_is_valid and not note_is_suitable:
                    reject_reason = "MODEL_NOTE_UNSUITABLE"
                elif note_is_valid and note_is_suitable and not is_new_note:
                    reject_reason = "DUPLICATE_NOTE"
                rejected_items.append({"text": note, "reason": reject_reason})
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

        deduped_rejected, rejected_stats = self._build_rejection_stats(node, rejected_items)
        node["rejected_candidates"] = deduped_rejected
        node["rejected_candidate_stats"] = rejected_stats

        for child in node.get("linguistic_elements", []):
            self._annotate_node(sentence_text, child, seen_notes)
