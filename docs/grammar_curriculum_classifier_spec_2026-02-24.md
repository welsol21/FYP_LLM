# Grammar Curriculum Classifier Spec

Date: 2026-02-24  
Status: Planned (TDD implementation)

## 1. Objective

Rebuild backend note quality pipeline from free-form note generation to:

1. **Classifier-first contract enrichment**
2. **Controlled note generation**

Core idea:
- classify each linguistic element into CEFR + grammar classes,
- store level-specific note blueprints,
- let T5 generate final user-facing note text from those blueprints.

## 1.1 Model Split Decision (Locked)

Approved model split for backend rebuild:

- **Classification stage (`CEFR + grammar_classes`)**: `DeBERTa-v3-base`
- **Generation stage (note text realization)**: `T5` (controlled generation only)

Why this decision:
- CEFR/grammar labeling is a classification task; encoder-only models are more stable and contract-safe here.
- T5 remains useful for controlled text rendering from classifier outputs/blueprints.
- This split reduces schema-risk (fewer free-form label errors) and improves deterministic validation behavior.

## 1.2 Time Impact vs T5-as-Classifier

Using `DeBERTa-v3-base` for classification instead of T5 classification is expected to:

- reduce ML-stage training/evaluation time by roughly `40-65%` (T5 is typically `1.7-2.8x` slower for label generation-style classification),
- reduce classifier inference latency by roughly `50-75%` (T5 is typically `2-4x` slower for this workload),
- reduce full-program delivery time by roughly `20-35%` due to faster iteration cycles and fewer contract-format failures in classification stage.

Important:
- major time consumption still remains in KB quality loops and gate retries, not in one model run.
- T5 runtime remains in scope only for note text generation.

## 2. Core Curriculum Backbone

Use the **English tense table** as curriculum core.

For each grammar class, build a strict level ladder:

`A1 -> A2 -> B1 -> B2 -> C1 -> C2`

This is applied per class, not globally.

## 2.1 Rollout Phases

Implementation is staged into three quality-gated phases:

1. **Phase 1 (Starter band):** `A1 -> A2 -> B1`
2. **Phase 2 (Expansion):** `B2`
3. **Phase 3 (Advanced):** `C1 -> C2`

Rule:
- next phase starts only after previous phase passes all stage gates for repeated runs.

## 3. Grammar Class Multiplicity

`Sentence` and `Phrase` nodes can have multiple grammar classes simultaneously.

Contract policy:
- `grammar_classes` is an array (many-to-many)
- each class entry contains:
  - `class_id`
  - `confidence`
  - optional `scope_span`
  - `note_blueprints` for all six levels

`Word` nodes may still use the same array shape for consistency.

## 4. Dataset Build Strategy

### 4.1 KB construction

Build a grammar KB with 3 pedagogical bands:
- Elementary (`A1-A2`)
- Intermediate (`B1-B2`)
- Advanced (`C1-C2`)

Each KB item includes:
- `grammar_class_id`
- canonical examples
- level mapping and blueprints
- provenance metadata

### 4.2 spaCy enrichment at scale

For every example, persist enriched features:
- token/lemma/POS/morph
- dependency + head
- phrase spans and TAM-oriented derived features

Output layers:
- `kb_raw`
- `kb_spacy_enriched`
- `kb_train_ready`

## 5. Quality Loop with Step Repetition

Pipeline is iterative, not one-shot:

`Generate -> Enrich -> Train -> Eval -> Diagnose -> Repair -> Repeat`

Each stage has hard quality gates.  
If a gate fails, repeat only the required stage (or previous stage), not the full run.

Implementation note:
- iterative loop runner is implemented in `ela_pipeline/classifier/iterative_loop.py`
- stopping criterion: required consecutive full-pass runs (`required_consecutive_passes`, default `3`)
- gate-level retry execution/telemetry is implemented in `ela_pipeline/classifier/quality_loop.py`

## 6. Stage Gates

1. **KB generation gate**
- class coverage
- level balance
- duplicate ratio
- invalid blueprint ratio

2. **spaCy enrichment gate**
- parse success rate
- required feature coverage
- structural anomaly rate

3. **classifier gate**
- macro F1
- per-class recall
- calibration metrics

4. **contract gate**
- schema validation pass rate
- CEFR + grammar class consistency
- mandatory blueprint completeness

5. **NLG gate**
- note relevance to predicted class
- level-appropriate style
- hallucination/contradiction rate

## 7. Feedback + Repair Logging

Persist quality telemetry:
- `quality_events` (stage, metric, threshold, pass/fail, run_id)
- `repair_actions` (what was regenerated/rebalanced/relabelled)

This enables deterministic improvement tracking and reproducibility.

## 8. Expected Iteration Scale

At project scale, expect **tens of thousands of micro-iterations**:
- sample-level enrichment/relabel retries,
- targeted regeneration cycles,
- hard-negative loops.

Macro training/evaluation cycles are smaller (typically dozens to low hundreds).

## 8.1 Time Estimates (Desktop Capacity Summary)

Approximate delivery windows:

- **Phase 1 (`A1 -> A2 -> B1`)**
  - MVP: `1.5-2.5 weeks`
  - stable quality: `3-4 weeks`
  - expected loop volume:
    - macro cycles: `30-90`
    - micro iterations: `6,000-35,000`

- **Phase 2 (`B2`)**
  - incremental extension after Phase 1: `1-2.5 weeks`
  - expected loop volume:
    - macro cycles: `15-45`
    - micro iterations: `3,000-20,000`

- **Phase 3 (`C1 -> C2`)**
  - advanced extension after Phase 2: `2-4 weeks`
  - expected loop volume:
    - macro cycles: `20-60`
    - micro iterations: `5,000-30,000`

Combined trajectory:
- first usable rollout (`A1-B1`) in ~`1.5-2.5 weeks`,
- full ladder (`A1-C2`) typically ~`6-10 weeks`, depending on gate failures and repair passes.

## 9. Implementation Policy

- TDD-first for each stage.
- No silent fallback that changes contract truth fields.
- T5 can rewrite note text only; it must not overwrite classifier truth fields.
