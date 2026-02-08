#!/usr/bin/env python3
"""
Inference for Sentence + Phrase + Word levels.
"""

import os
import sys
from typing import List, Dict, Any

import torch
import spacy
from transformers import T5Tokenizer, T5ForConditionalGeneration

MODEL_DIR = "./results_llm_notes_v3_t5-small_phrase/best_model"
SPACY_MODEL = "en_core_web_sm"

device = torch.device("cpu")
MAX_INPUT_LENGTH = 512
MAX_TARGET_LENGTH = 128


# -----------------------------
# LOAD MODELS
# -----------------------------
def load_models():
    tokenizer = T5Tokenizer.from_pretrained(MODEL_DIR)
    model = T5ForConditionalGeneration.from_pretrained(MODEL_DIR).to(device)
    model.eval()

    nlp = spacy.load(SPACY_MODEL)
    if "sentencizer" not in nlp.pipe_names:
        nlp.add_pipe("sentencizer")

    return tokenizer, model, nlp


# -----------------------------
# HELPERS
# -----------------------------
def format_feature_list(features: List[str]) -> str:
    return ", ".join(features).replace("|", ":")


def format_morph(token):
    return format_feature_list(list(token.morph))


# -----------------------------
# BUILD INPUTS
# -----------------------------
def build_llm_inputs(text: str, nlp):
    doc = nlp(text)
    examples = []

    # Sentence-level
    for sent in doc.sents:
        pos_list = [t.pos_ for t in sent if not t.is_space]
        dep_list = [t.dep_ for t in sent if not t.is_space]

        llm_input = (
            f"pos: {format_feature_list(pos_list)} "
            f"dep: {format_feature_list(dep_list)} "
            f"sentence: {sent.text}"
        )
        examples.append({"level": "Sentence", "original": sent.text, "llm_input": llm_input})

        # Phrase-level (NP chunks)
        for chunk in sent.noun_chunks:
            pos_list = [t.pos_ for t in chunk]
            dep_list = [t.dep_ for t in chunk]

            llm_input = (
                f"pos: {format_feature_list(pos_list)} "
                f"dep: {format_feature_list(dep_list)} "
                f"chunk: NP "
                f"phrase: {chunk.text}"
            )
            examples.append({"level": "Phrase", "original": chunk.text, "llm_input": llm_input})

        # Word-level
        for token in sent:
            if token.is_space:
                continue

            llm_input = (
                f"pos: {token.pos_} "
                f"tag: {token.tag_} "
                f"dep: {token.dep_} "
                f"morph: {format_morph(token)} "
                f"word: {token.text}"
            )
            examples.append({"level": "Word", "original": token.text, "llm_input": llm_input})

    return examples


# -----------------------------
# GENERATION
# -----------------------------
def generate_notes(llm_input, tokenizer, model):
    enc = tokenizer(llm_input, return_tensors="pt", truncation=True, max_length=MAX_INPUT_LENGTH)
    enc = {k: v.to(device) for k, v in enc.items()}

    with torch.no_grad():
        out = model.generate(**enc, max_length=MAX_TARGET_LENGTH, num_beams=1)

    return tokenizer.decode(out[0], skip_special_tokens=True)


# -----------------------------
# MAIN
# -----------------------------
if __name__ == "__main__":
    tokenizer, model, nlp = load_models()

    text = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "I like to eat pizza."

    examples = build_llm_inputs(text, nlp)

    # Generate notes for each example
    results = []
    for i, ex in enumerate(examples):
        notes = generate_notes(ex["llm_input"], tokenizer, model)
        item = {
            "level": ex["level"],
            "original": ex["original"],
            "llm_input": ex["llm_input"],
            "linguistic_notes": notes,
        }
        results.append(item)

        # Pretty print first 30 items
        if i < 30:
            print("=" * 80)
            print(f"[{i+1}] Level: {ex['level']}")
            print(f"Original: {ex['original']}")
            print(f"LLM input: {ex['llm_input']}")
            print("Generated notes:")
            print(notes)
            print()

    # -----------------------------
    # SAVE RESULTS TO JSON
    # -----------------------------
    import json
    from datetime import datetime

    os.makedirs("inference_results", exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"inference_results/linguistic_notes_{timestamp}.json"

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\nSaved results to: {filename}\n")
