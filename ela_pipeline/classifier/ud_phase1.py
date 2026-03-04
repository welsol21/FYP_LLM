"""UD-backed Phase 1 helpers: local CoNLL-U ingest and hard dataset gates."""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .audit_phase1_dataset import audit_classifier_dataset


def _parse_feats(raw: str) -> dict[str, str]:
    value = str(raw or "").strip()
    if not value or value == "_":
        return {}
    feats: dict[str, str] = {}
    for part in value.split("|"):
        if "=" not in part:
            continue
        key, feat_value = part.split("=", 1)
        key = key.strip()
        feat_value = feat_value.strip()
        if key and feat_value:
            feats[key] = feat_value
    return feats


def load_ud_conllu(*, input_path: str, treebank: str, split: str) -> list[dict[str, Any]]:
    src = Path(input_path)
    if not src.is_file():
        raise FileNotFoundError(f"UD CoNLL-U file not found: {input_path}")

    rows: list[dict[str, Any]] = []
    metadata: dict[str, str] = {}
    document_metadata: dict[str, str] = {}
    tokens: list[dict[str, Any]] = []
    doc_level_keys = {"newdoc id", "newdoc_id", "meta::genre"}

    def flush() -> None:
        nonlocal metadata, tokens
        if not tokens:
            metadata = {}
            return
        merged_metadata = {**document_metadata, **metadata}
        text = str(merged_metadata.get("text") or "").strip()
        sent_id = str(merged_metadata.get("sent_id") or "").strip()
        doc_id = str(merged_metadata.get("newdoc id") or merged_metadata.get("newdoc_id") or "").strip()
        genre = str(merged_metadata.get("meta::genre") or "").strip().lower()
        rows.append(
            {
                "text": text,
                "tokens": tokens,
                "provenance": {
                    "treebank": treebank,
                    "split": split,
                    "sent_id": sent_id,
                    "doc_id": doc_id,
                    "genre": genre,
                    "source_path": str(src),
                },
            }
        )
        metadata = {}
        tokens = []

    with src.open("r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.rstrip("\n")
            if not line.strip():
                flush()
                continue
            if line.startswith("#"):
                if "=" in line:
                    key, value = line[1:].split("=", 1)
                    key = key.strip()
                    value = value.strip()
                    metadata[key] = value
                    if key in doc_level_keys:
                        document_metadata[key] = value
                continue
            parts = line.split("\t")
            if len(parts) != 10:
                continue
            token_id = parts[0].strip()
            if "-" in token_id or "." in token_id:
                continue
            head_raw = parts[6].strip()
            try:
                token_index = int(token_id)
            except ValueError:
                continue
            try:
                head_index = int(head_raw) if head_raw and head_raw != "_" else 0
            except ValueError:
                head_index = 0
            tokens.append(
                {
                    "id": token_index,
                    "text": parts[1],
                    "lemma": parts[2],
                    "upos": parts[3],
                    "xpos": parts[4],
                    "morph": _parse_feats(parts[5]),
                    "head": head_index,
                    "dep": parts[7],
                }
            )
    flush()
    return rows


def extract_phase1_grammar_signal(row: dict[str, Any]) -> dict[str, Any]:
    tokens = row.get("tokens")
    if not isinstance(tokens, list):
        return {"grammar_classes": [], "tam_profile": "unknown", "finite_root": None}

    token_rows = [tok for tok in tokens if isinstance(tok, dict)]
    finite_root: dict[str, Any] | None = None
    for token in token_rows:
        if str(token.get("dep") or "").strip() != "root":
            continue
        morph = token.get("morph")
        if isinstance(morph, dict) and str(morph.get("VerbForm") or "").strip() == "Fin":
            finite_root = token
            break
        if str(token.get("upos") or "").strip() in {"VERB", "AUX"}:
            finite_root = token
            break

    grammar_classes: list[str] = []
    tam_profile = "unknown"

    def _child_auxiliaries(head_id: int) -> list[dict[str, Any]]:
        return [
            tok
            for tok in token_rows
            if str(tok.get("upos") or "").strip() == "AUX" and int(tok.get("head") or 0) == head_id
        ]

    def _detect_priority_pattern() -> tuple[str | None, str | None]:
        priority_candidates: list[tuple[int, str, str]] = []
        for token in token_rows:
            upos = str(token.get("upos") or "").strip()
            xpos = str(token.get("xpos") or "").strip().upper()
            if upos not in {"VERB", "AUX"} or xpos != "VBN":
                continue
            head_id = int(token.get("id") or 0)
            auxiliaries = _child_auxiliaries(head_id)
            aux_lemmas = {str(tok.get("lemma") or "").strip().lower() for tok in auxiliaries}
            modal_perfect_lemmas = {"should", "could", "would", "might", "may", "must", "can"}
            has_have_aux = "have" in aux_lemmas
            has_future_modal = bool({"will", "shall"}.intersection(aux_lemmas))
            has_modal_perfect = bool(modal_perfect_lemmas.intersection(aux_lemmas)) and has_have_aux
            if has_future_modal and has_have_aux:
                priority_candidates.append((head_id, "future_perfect", "future_perfect"))
            elif has_modal_perfect:
                priority_candidates.append((head_id, "modal_perfect", "modal_perfect"))
        if not priority_candidates:
            return None, None
        priority_candidates.sort(key=lambda item: item[0])
        _, cls, profile = priority_candidates[0]
        return cls, profile

    priority_class, priority_profile = _detect_priority_pattern()
    if priority_class:
        grammar_classes.append(priority_class)
        tam_profile = str(priority_profile)

    if finite_root:
        morph = finite_root.get("morph") if isinstance(finite_root.get("morph"), dict) else {}
        tense = str(morph.get("Tense") or "").strip()
        lemma = str(finite_root.get("lemma") or "").strip().lower()
        xpos = str(finite_root.get("xpos") or "").strip().upper()
        root_id = int(finite_root.get("id") or 0)
        auxiliaries = _child_auxiliaries(root_id)
        aux_lemmas = {str(tok.get("lemma") or "").strip().lower() for tok in auxiliaries}
        aux_forms = {str(tok.get("xpos") or "").strip().upper() for tok in auxiliaries}
        has_neg = any(
            str(tok.get("dep") or "").strip() in {"advmod", "neg"} and str(tok.get("lemma") or "").strip().lower() == "not"
            for tok in token_rows
        )
        has_aux = bool(auxiliaries)
        has_progressive_aux = any(
            str(tok.get("lemma") or "").strip().lower() == "be"
            for tok in auxiliaries
        )
        has_have_aux = any(
            str(tok.get("lemma") or "").strip().lower() == "have"
            for tok in auxiliaries
        )
        has_relative_clause = any(str(tok.get("dep") or "").strip() == "acl:relcl" for tok in token_rows)
        has_question_punct = any(str(tok.get("text") or "").strip() == "?" for tok in token_rows)
        has_do_aux = "do" in aux_lemmas
        has_modal_will = bool({"will", "shall"}.intersection(aux_lemmas)) or (
            "MD" in aux_forms
            and any(str(tok.get("lemma") or "").strip().lower() in {"will", "shall"} for tok in auxiliaries)
        )
        has_modal_can = "can" in aux_lemmas
        has_modal_should = "should" in aux_lemmas
        modal_perfect_lemmas = {"should", "could", "would", "might", "may", "must", "can"}
        has_modal_perfect = bool(modal_perfect_lemmas.intersection(aux_lemmas)) and has_have_aux and xpos == "VBN"
        has_auxpass = any(str(tok.get("dep") or "").strip() == "aux:pass" for tok in auxiliaries)
        has_nsubjpass = any(str(tok.get("dep") or "").strip() in {"nsubj:pass", "csubj:pass"} for tok in token_rows)
        has_to_inf_xcomp = any(
            str(tok.get("dep") or "").strip() == "xcomp" and str(tok.get("xpos") or "").strip().upper() == "VB"
            for tok in token_rows
        ) and any(str(tok.get("lemma") or "").strip().lower() == "to" for tok in token_rows)

        if priority_class:
            pass
        elif has_relative_clause:
            tam_profile = "relative_clause"
            grammar_classes.append("relative_clause")
        elif has_modal_will and has_have_aux and xpos == "VBN":
            tam_profile = "future_perfect"
            grammar_classes.append("future_perfect")
        elif has_modal_perfect:
            tam_profile = "modal_perfect"
            grammar_classes.append("modal_perfect")
        elif has_have_aux and any(str(tok.get("xpos") or "").strip().upper() == "VBD" for tok in auxiliaries) and xpos == "VBN":
            tam_profile = "past_perfect"
            grammar_classes.append("past_perfect")
        elif (has_auxpass or has_nsubjpass) and xpos == "VBN":
            tam_profile = "passive_voice"
            grammar_classes.append("passive_voice")
        elif has_modal_should:
            tam_profile = "modal_should"
            grammar_classes.append("modal_should_advice")
        elif has_modal_can:
            tam_profile = "modal_can"
            grammar_classes.append("modal_can_ability")
        elif has_modal_will:
            tam_profile = "future_will"
            grammar_classes.append("future_will")
        elif lemma == "go" and has_progressive_aux and has_to_inf_xcomp:
            tam_profile = "future_going_to"
            grammar_classes.append("future_going_to")
        elif has_do_aux and has_question_punct:
            tam_profile = "present_simple"
            grammar_classes.append("present_simple_question")
        elif has_have_aux and xpos == "VBN":
            tam_profile = "present_perfect"
            grammar_classes.append("present_perfect_negative" if has_neg else "present_perfect_affirmative")
        elif tense == "Pres" and xpos in {"VB", "VBP", "VBZ"}:
            tam_profile = "present_simple"
            grammar_classes.append("present_simple_negative" if has_neg else "present_simple_affirmative")
        elif tense == "Past" and xpos in {"VBD", "VBN"} and lemma != "be":
            tam_profile = "past_simple"
            grammar_classes.append("past_simple_negative" if has_neg else "past_simple_affirmative")
        elif str(morph.get("VerbForm") or "").strip() == "Part" and has_progressive_aux:
            tam_profile = "present_continuous"
            grammar_classes.append("present_continuous")
        elif has_aux and lemma == "be":
            tam_profile = "be_copula"
            grammar_classes.append("copular_clause")

    dep_signature = [str(tok.get("dep") or "").strip() for tok in token_rows]
    pos_signature = [str(tok.get("upos") or "").strip() for tok in token_rows]

    return {
        "grammar_classes": sorted(set(grammar_classes)),
        "tam_profile": tam_profile,
        "finite_root": finite_root,
        "grammar_evidence": {
            "dep_signature": dep_signature,
            "pos_signature": pos_signature,
            "token_count": len(tokens),
        },
    }


def validate_phase1_dataset_gates(
    rows: list[dict[str, Any]],
    *,
    max_ambiguous_grammar_combo_ratio: float = 0.05,
    max_exact_text_cross_level_ratio: float = 0.01,
    min_examples_per_class: int = 1,
) -> dict[str, Any]:
    combo_to_levels: dict[tuple[str, ...], Counter[str]] = defaultdict(Counter)
    text_to_levels: dict[str, set[str]] = defaultdict(set)
    class_support: Counter[tuple[str, str]] = Counter()
    evidence_missing = 0
    blueprint_missing = 0

    for row in rows:
        cefr = str(row.get("cefr_level") or "").strip().upper()
        text = str(row.get("text") or "").strip()
        grammar_classes = row.get("grammar_classes")
        grammar_evidence = row.get("grammar_evidence")
        note_blueprints = row.get("note_blueprints")

        if not isinstance(grammar_evidence, dict) or not grammar_evidence:
            evidence_missing += 1

        elementary = intermediate = advanced = ""
        if isinstance(note_blueprints, dict):
            elementary = str(
                note_blueprints.get("elementary_text")
                or note_blueprints.get("elementary")
                or ""
            ).strip()
            intermediate = str(
                note_blueprints.get("intermediate_text")
                or note_blueprints.get("intermediate")
                or ""
            ).strip()
            advanced = str(
                note_blueprints.get("advanced_text")
                or note_blueprints.get("advanced")
                or ""
            ).strip()
        if not (elementary and intermediate and advanced):
            blueprint_missing += 1

        if not cefr or not isinstance(grammar_classes, list):
            continue
        combo = tuple(sorted(str(x).strip().lower() for x in grammar_classes if str(x).strip()))
        if not combo:
            evidence_missing += 1
            continue
        combo_to_levels[combo][cefr] += 1
        if text:
            text_to_levels[text].add(cefr)
        for class_id in combo:
            class_support[(class_id, cefr)] += 1

    unique_combo_count = len(combo_to_levels)
    ambiguous_combo_count = sum(1 for levels in combo_to_levels.values() if len(levels) > 1)
    ambiguous_combo_ratio = (ambiguous_combo_count / unique_combo_count) if unique_combo_count else 0.0
    exact_text_cross_level_count = sum(1 for levels in text_to_levels.values() if len(levels) > 1)
    exact_text_cross_level_ratio = (
        exact_text_cross_level_count / len(text_to_levels) if text_to_levels else 0.0
    )
    insufficient_support = [
        {"class_id": class_id, "cefr_level": cefr, "count": count}
        for (class_id, cefr), count in sorted(class_support.items())
        if count < min_examples_per_class
    ]

    failed_gates: list[str] = []
    if ambiguous_combo_ratio > max_ambiguous_grammar_combo_ratio:
        failed_gates.append("grammar_combo_ambiguity")
    if exact_text_cross_level_ratio > max_exact_text_cross_level_ratio:
        failed_gates.append("exact_text_cross_level")
    if insufficient_support:
        failed_gates.append("per_class_support")
    if evidence_missing:
        failed_gates.append("evidence_completeness")
    if blueprint_missing:
        failed_gates.append("blueprint_completeness")

    return {
        "passed": not failed_gates,
        "failed_gates": failed_gates,
        "samples": len(rows),
        "unique_grammar_combos": unique_combo_count,
        "ambiguous_grammar_combo_count": ambiguous_combo_count,
        "ambiguous_grammar_combo_ratio": ambiguous_combo_ratio,
        "exact_text_cross_level_count": exact_text_cross_level_count,
        "exact_text_cross_level_ratio": exact_text_cross_level_ratio,
        "evidence_missing_count": evidence_missing,
        "blueprint_missing_count": blueprint_missing,
        "insufficient_support": insufficient_support[:25],
    }


def validate_phase1_dataset_gates_from_jsonl(
    *,
    dataset_path: str,
    max_ambiguous_grammar_combo_ratio: float = 0.05,
    max_exact_text_cross_level_ratio: float = 0.01,
    min_examples_per_class: int = 1,
) -> dict[str, Any]:
    audit = audit_classifier_dataset(dataset_path=dataset_path)
    rows_path = Path(dataset_path)
    rows: list[dict[str, Any]] = []
    import json

    with rows_path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    report = validate_phase1_dataset_gates(
        rows,
        max_ambiguous_grammar_combo_ratio=max_ambiguous_grammar_combo_ratio,
        max_exact_text_cross_level_ratio=max_exact_text_cross_level_ratio,
        min_examples_per_class=min_examples_per_class,
    )
    report["audit"] = audit
    return report
