"""Quick inference demo for rle_v3 model.

Shows Sentence, Phrase, and Word contracts for one example sentence.
"""
from __future__ import annotations

import json
import sys

import torch
from transformers import T5ForConditionalGeneration, T5Tokenizer

MODEL_DIR = "artifacts/models/t5_notes_rle_v5/best_model"
TASK_NAME = "generate_linguistic_note"
PROMPT_TEMPLATE_VERSION = "rle_v5"

MAX_INPUT = 512
MAX_TARGET = 128


def load_model(model_dir: str):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    tokenizer = T5Tokenizer.from_pretrained(model_dir)
    model = T5ForConditionalGeneration.from_pretrained(model_dir).to(device)
    model.eval()
    return tokenizer, model, device


def generate(tokenizer, model, device, input_text: str) -> str:
    enc = tokenizer(input_text, return_tensors="pt", truncation=True, max_length=MAX_INPUT)
    enc = {k: v.to(device) for k, v in enc.items()}
    with torch.no_grad():
        out = model.generate(**enc, max_length=MAX_TARGET, num_beams=4)
    return tokenizer.decode(out[0], skip_special_tokens=True).strip()


def make_input(payload: dict) -> str:
    payload["prompt_template_version"] = PROMPT_TEMPLATE_VERSION
    payload["task"] = TASK_NAME
    return f"task: {TASK_NAME} payload: {json.dumps(payload, ensure_ascii=False, sort_keys=True)}"


def sentence_input(content: str, tense: str, aspect: str, voice: str, tam: str) -> str:
    return make_input({
        "node_type": "Sentence",
        "content": content,
        "part_of_speech": "VERB",
        "grammatical_role": "ROOT",
        "tense": tense,
        "aspect": aspect,
        "mood": "null",
        "voice": voice,
        "tam_construction": tam,
    })



def word_input(word: str, pos: str) -> str:
    return make_input({
        "node_type": "Word",
        "content": word,
        "part_of_speech": pos,
        "grammatical_role": "dep",
    })


def main() -> None:
    import os
    os.chdir("/home/vlad/Dev/FYP_LLM")

    from ela_pipeline.parse.spacy_parser import load_nlp
    from ela_pipeline.tam.rules import detect_tam

    print("Loading models...")
    tokenizer, model, device = load_model(MODEL_DIR)
    nlp = load_nlp("en_core_web_sm")

    sentence = "The letter was written by John after the meeting had ended."
    print(f"\n{'='*70}")
    print(f"Sentence: {sentence}")
    print(f"{'='*70}\n")

    # --- Sentence contract ---
    doc = nlp(sentence)
    tam = detect_tam(doc)
    label = tam.label or ""
    tense = tam.short_tense or "null"
    voice = "passive" if "passive" in label else "active"
    if "perfect_progressive" in label:
        aspect = "perfect_progressive"
    elif "perfect" in label:
        aspect = "perfect"
    elif "progressive" in label:
        aspect = "progressive"
    else:
        aspect = "simple"

    # Build content: immediate children of ROOT as simplified node stubs
    root = next((t for t in doc if t.dep_ == "ROOT"), None)
    children = [c for c in (root.children if root else []) if not c.is_punct]
    content = json.dumps([
        {"content": "{{PHRASE}}" if list(c.children) else "{{WORD}}",
         "grammatical_role": c.dep_,
         "node_type": "Phrase" if list(c.children) else "Word",
         "part_of_speech": c.pos_}
        for c in children
    ], sort_keys=True)

    s_inp = sentence_input(content, tense, aspect, voice, label)
    s_out = generate(tokenizer, model, device, s_inp)
    print(f"[SENTENCE]  tam={label!r}  tense={tense}  aspect={aspect}  voice={voice}")
    print(f"  NOTE: {s_out}\n")

    # --- Phrase contracts: extract real phrases from the sentence ---
    from ela_pipeline.dataset.build_t5_dataset_v22_book_pairs import (
        _build_node_contract,
        _build_phrase_input_from_elements,
        _build_vp_elements,
        _find_phrase_heads,
    )

    PHRASE_DEMO_TOPICS = [
        ("noun_phrase",           "NOUN phrase"),
        ("verb_phrase",           "VERB phrase"),
        ("prepositional_phrases", "ADP phrase"),
    ]
    print("[PHRASES]")
    for topic_key, label_str in PHRASE_DEMO_TOPICS:
        heads = _find_phrase_heads(doc, topic_key)
        if not heads:
            print(f"  [{label_str}]  no phrase found in sentence\n")
            continue
        for head in heads[:2]:
            if topic_key == "verb_phrase":
                elements = _build_vp_elements(head)
                vp_span = " ".join(
                    t.text for t in sorted(
                        [c for c in head.children if c.dep_ in {"aux", "auxpass", "neg"}] + [head],
                        key=lambda t: t.i,
                    )
                )
                span = vp_span
            else:
                contract = _build_node_contract(head, "", depth=0, max_depth=2)
                elements = contract.get("linguistic_elements")
                span = " ".join(t.text for t in head.subtree if not t.is_punct)
            if not elements:
                continue
            content = json.dumps(elements, ensure_ascii=False, sort_keys=True)
            p_inp = _build_phrase_input_from_elements(content, head.pos_, head.dep_)
            p_out = generate(tokenizer, model, device, p_inp)
            print(f"  [{label_str}]  span='{span}'  pos={head.pos_}  dep={head.dep_}")
            print(f"    NOTE: {p_out}")
        print()

    # --- Word contracts ---
    word_tests = []
    for token in doc:
        if token.is_punct or token.is_space:
            continue
        word_tests.append((token.lemma_, token.pos_))

    seen = set()
    print("[WORDS]")
    for lemma, pos in word_tests:
        key = (lemma, pos)
        if key in seen:
            continue
        seen.add(key)
        w_inp = word_input(lemma, pos)
        w_out = generate(tokenizer, model, device, w_inp)
        print(f"  {lemma!r:12s} ({pos:6s}) → {w_out}")


if __name__ == "__main__":
    main()
