#!/usr/bin/env python3
"""
Inference script for fine-tuned T5 that generates `linguistic_notes`.

Works with local training output:
  ./results_llm_notes_v3_t5-small_cpu/best_model
(or point MODEL_DIR to your folder)

Windows / CPU-friendly.
"""

import os
import sys
from typing import List, Dict, Any

import torch
import spacy
from transformers import T5Tokenizer, T5ForConditionalGeneration


# -----------------------------
# 1. CONFIG & MODEL LOADING
# -----------------------------

# <<< IMPORTANT: set this to your actual BEST_MODEL_DIR >>>
MODEL_DIR = r"./results_llm_notes_v3_t5-small_cpu/best_model"
SPACY_MODEL = "en_core_web_sm"

MAX_INPUT_LENGTH = 512
MAX_TARGET_LENGTH = 128

# You trained on CPU; inference on CPU is fine (and stable).
device = torch.device("cpu")


def load_models():
    """Load fine-tuned T5 model, tokenizer and spaCy pipeline."""
    if not os.path.isdir(MODEL_DIR):
        print(f"❌ Model directory not found: {MODEL_DIR}")
        print(
            "   Tip: check that best_model contains config.json + model weights + tokenizer files."
        )
        sys.exit(1)

    try:
        tokenizer = T5Tokenizer.from_pretrained(MODEL_DIR)
        model = T5ForConditionalGeneration.from_pretrained(MODEL_DIR)
        model.to(device)
        model.eval()
    except Exception as e:
        print(f"❌ Error while loading T5 model from {MODEL_DIR}: {e}")
        sys.exit(1)

    try:
        nlp = spacy.load(SPACY_MODEL)
        # Ensure sentence boundaries exist
        if "parser" not in nlp.pipe_names and "senter" not in nlp.pipe_names:
            if "sentencizer" not in nlp.pipe_names:
                nlp.add_pipe("sentencizer")
    except Exception as e:
        print(f"❌ Error while loading spaCy model '{SPACY_MODEL}': {e}")
        print("   If missing: python -m spacy download en_core_web_sm")
        sys.exit(1)

    print(f"✅ T5 model loaded from {MODEL_DIR}")
    print(f"✅ spaCy model '{SPACY_MODEL}' loaded")
    print(f"✅ device = {device}")
    return tokenizer, model, nlp


# -----------------------------
# 2. BUILD LLM INPUTS (match training format)
# -----------------------------


def format_feature_list(features: List[str]) -> str:
    """Same formatting as in training: comma-separated, '|' replaced with ':'."""
    return ", ".join(features).replace("|", ":")


def format_morph(token) -> str:
    """
    In training you used something like `format_feature_list(wf.get("morph", []))`.
    For spaCy token.morph, we convert to feature list like:
        ["Case=Nom", "Number=Sing", ...]
    and then format_feature_list() to match training.
    """
    feats = list(token.morph)  # e.g. ["Number=Sing", "Tense=Pres"]
    return format_feature_list(feats)


def build_llm_inputs_from_text(text: str, nlp) -> List[Dict[str, Any]]:
    doc = nlp(text)
    examples: List[Dict[str, Any]] = []

    # Sentence loop
    for sent in doc.sents:
        sent_text = sent.text.strip()
        if not sent_text:
            continue

        pos_list = [t.pos_ for t in sent if not t.is_space]
        dep_list = [t.dep_ for t in sent if not t.is_space]

        sent_pos = format_feature_list(pos_list)
        sent_dep = format_feature_list(dep_list)

        llm_input_sentence = f"pos: {sent_pos} dep: {sent_dep} sentence: {sent_text}"

        examples.append(
            {
                "level": "Sentence",
                "original": sent_text,
                "llm_input": llm_input_sentence,
            }
        )

        # Word-level: exactly like training: pos/tag/dep/morph/word
        for token in sent:
            if token.is_space:
                continue

            pos = token.pos_ or "UNKNOWN"
            tag = token.tag_ or "UNKNOWN"
            dep = token.dep_ or "UNKNOWN"
            morph = format_morph(token)  # <-- important change vs str(token.morph)
            word_text = token.text

            llm_input_word = (
                f"pos: {pos} "
                f"tag: {tag} "
                f"dep: {dep} "
                f"morph: {morph} "
                f"word: {word_text}"
            )

            examples.append(
                {"level": "Word", "original": word_text, "llm_input": llm_input_word}
            )

    return examples


# -----------------------------
# 3. T5 INFERENCE
# -----------------------------


def generate_linguistic_notes(
    llm_input: str,
    tokenizer: T5Tokenizer,
    model: T5ForConditionalGeneration,
    max_target_length: int = MAX_TARGET_LENGTH,
) -> str:
    enc = tokenizer(
        llm_input,
        return_tensors="pt",
        truncation=True,
        max_length=MAX_INPUT_LENGTH,
    )
    enc = {k: v.to(device) for k, v in enc.items()}

    with torch.no_grad():
        output_ids = model.generate(
            **enc,
            max_length=max_target_length,
            num_beams=1,
        )

    return tokenizer.decode(output_ids[0], skip_special_tokens=True)


def analyse_text(
    text: str,
    tokenizer: T5Tokenizer,
    model: T5ForConditionalGeneration,
    nlp,
    max_items: int = 20,
) -> List[Dict[str, Any]]:
    print(f"\n⚙️ Analysing text with length {len(text)} characters...\n")

    examples = build_llm_inputs_from_text(text, nlp)
    if not examples:
        print("⚠️ No sentences found in the text.")
        return []

    results: List[Dict[str, Any]] = []

    for idx, ex in enumerate(examples):
        notes = generate_linguistic_notes(ex["llm_input"], tokenizer, model)
        result_item = {
            "level": ex["level"],
            "original": ex["original"],
            "llm_input": ex["llm_input"],
            "linguistic_notes": notes,
        }
        results.append(result_item)

        if idx < max_items:
            print("=" * 80)
            print(f"[{idx+1}] Level: {ex['level']}")
            print(f"Original: {ex['original']}")
            print(f"LLM input: {ex['llm_input']}")
            print(f"Generated notes:\n{notes}\n")

    if len(examples) > max_items:
        print(f"... ({len(examples) - max_items} more items not printed)")

    return results


# -----------------------------
# 4. MAIN
# -----------------------------

if __name__ == "__main__":
    tokenizer, model, nlp = load_models()

    if len(sys.argv) > 1:
        input_text = " ".join(sys.argv[1:])
    else:
        input_text = "I like to eat pizza."

    results = analyse_text(input_text, tokenizer, model, nlp)

    # Save to JSON if you want
    # import json
    # with open("t5_linguistic_notes_output.json", "w", encoding="utf-8") as f:
    #     json.dump(results, f, ensure_ascii=False, indent=2)
