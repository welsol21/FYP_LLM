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

### 4.0 Phase 1 Dataset Recovery Decision (2026-03-03)

The first synthetic Phase 1 dataset (`A1 -> A2 -> B1`) is rejected as the training source for the classifier-first backend.

Reason:
- dataset audit showed severe CEFR ambiguity for the same grammar combinations,
- the trained DeBERTa classifier collapsed into a single class on validation,
- therefore the issue is in supervision/data quality, not just in training hyperparameters.

Implication:
- the current synthetic Phase 1 dataset must not be used as the runtime truth-layer source,
- retraining on the same source is not considered a meaningful fix,
- Phase 1 must be rebuilt on top of a real structural corpus with hard ambiguity gates.

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

### 4.1.1 UD-backed structural backbone

Use Universal Dependencies as the structural backbone for real sentence sources:

- primary source: `UD_English-EWT`
- optional expansion source: `UD_English-GUM`
- learner-language source `UD_English-ESL` is kept separate from baseline training and may be used only as controlled augmentation

Universal Dependencies is used for:
- real English sentence text,
- gold tokenization,
- POS / morphology / dependency structure,
- reproducible provenance.

Universal Dependencies is **not** treated as a ready CEFR dataset.

Therefore the project must add a mapping layer on top of UD:
- `UD structure -> grammar classes`
- `grammar evidence -> CEFR rung (Phase 1 only: A1/A2/B1)`
- `accepted class/rung -> note blueprints`

### 4.1.2 Advanced-register backbone for `B2 -> C1 -> C2`

Universal Dependencies alone is not enough for strong advanced-level coverage.

Observed limitation from real runs:
- `UD_English-EWT + UD_English-GUM` already gives a usable lower/mid ladder,
- but `C1/C2` support remains too small for reliable training,
- therefore advanced coverage must be strengthened with an additional source that contains more formal, academic, and high-register prose.

Approved next source layer:

- `OANC` / `Open American National Corpus`
  - role: main advanced-register source for `B2/C1/C2`
  - expected value: more formal prose, journalism, academic-like text, broader adult written register
  - usage in project: advanced training-source expansion, not a drop-in CEFR dataset
  - current ingestion policy: use the main `OANC-1.0.1-UTF8` corpus package and generate modern dependency parses locally during ingestion; do not depend on the historical `ANC-parses` archive

- `MASC`
  - role: smaller but higher-quality control/validation source
  - expected value: manually enriched annotation layer for validation and error analysis
  - usage in project: validation/calibration slice first, optional targeted augmentation later

Practical policy:
- `UD` remains the baseline structural backbone for broad grammar coverage.
- `OANC` strengthens advanced register coverage.
- `MASC` is treated as a quality-oriented validation/control source, not bulk training by default.
- `UD_English-GUM` must also be evaluated in a genre-aware way, not only as a generic merged treebank, because its higher-register genres are more informative for advanced coverage than its conversational and informal slices.
- `PMC OA` is the next bounded scientific-text expansion path for `C1/C2`; ingest should preserve article/license provenance from source XML before any parsing/enrichment step.
- `Project Gutenberg` is now the primary next expansion path for `C1/C2`, because essays and literary prose are a better genre match for `modal_perfect` and `future_perfect` than scientific articles.

Operational note:
- the legacy `ANC-parses` download is treated as unavailable/dead and is not a project dependency,
- dependency structure for `OANC` must be generated locally from the downloaded corpus package using the current parser stack.

Current project state:
- the package `OANC-1.0.1-UTF8.zip` has already been downloaded into `data/external_datasets/OANC/`,
- zip inspection is now implemented inside the project and recorded in `docs/reports/oanc_zip_inspection_2026-03-03.json`,
- the first inspection pass found `5999` advanced candidate `.txt` files across the targeted `journal`, `technical`, and `non-fiction` buckets.
- a bounded candidate-ingest pass is now implemented and recorded in `docs/reports/oanc_sentence_candidates_2026-03-04.json`,
- current status: file-level ingest and provenance are working, OANC sentence boundaries are now read from the corpus `*-s.xml` annotations when available, and local dependency parsing with parser provenance is implemented for the resulting candidate sentences,
- parsed `OANC` sentence candidates are now convertible into train-ready advanced rows, and the first bounded probe is recorded in `docs/reports/oanc_advanced_probe_2026-03-04.json`,
- first bounded probe result:
  - advanced mapped samples before final gate acceptance: `427`
  - gate outcome: `failed`
  - reason: `per_class_support`
  - concrete blocker: `future_perfect / C2` had only `1` accepted example in the bounded sample,
- targeted rare-pattern harvesting is now also implemented and probed in `docs/reports/oanc_targeted_pattern_search_2026-03-04.json` and `docs/reports/oanc_advanced_targeted_probe_2026-03-04.json`,
- targeted probe result:
  - selected targeted files: `48`
  - advanced mapped samples before final gate acceptance: `13`
  - gate outcome: `failed`
  - blockers:
    - `future_perfect / C2`: `1`
    - `modal_perfect / C1`: `1`
- the package `masc-conll.zip` has now been downloaded into `data/external_datasets/MASC/` and wired into a parser-backed validation/control ingest path,
- the full package `MASC-3.0.0.zip` has also been downloaded into `data/external_datasets/MASC/` for provenance capture and future richer ingest,
- package inventory from the full download is recorded in `docs/reports/masc_package_inventory_2026-03-04.json`,
- first `MASC` advanced probe is recorded in `docs/reports/masc_advanced_probe_2026-03-04.json`,
- current `MASC` probe result:
  - sentence candidates from `masc-conll`: `2288`
  - advanced mapped samples before final gate acceptance: `25`
  - gate outcome: `failed`
  - blocker:
    - `modal_perfect / C1`: `1`
- interpretation:
  - `MASC` is now confirmed as a useful validation/control source,
  - but it does not by itself repair `C1/C2` support gaps,
  - therefore `MASC` complements `OANC`; it does not replace the need for stronger rare advanced-pattern harvesting.
- merged advanced readiness report is now published in `docs/reports/advanced_coverage_report_2026-03-04.json`,
- targeted `OANC` harvest logic has been corrected so that the downstream probe uses the full matched `member_paths` set rather than only the truncated `examples` preview stored in the report,
- after that correction, the targeted `OANC` probe result increased from the earlier undercounted sample to:
  - `141` accepted advanced rows
  - `B2: 135`
  - `C1: 4`
  - `C2: 2`
  - elapsed probe time on the current targeted pool (`119` files): about `127s`
- current readiness result:
  - `B2 / past_perfect`: ready
  - `B2 / passive_voice`: ready
  - `C1 / modal_perfect`: not ready (`30 < 50` required train support)
  - `C2 / future_perfect`: not ready (`7 < 50` required train support)
- a dedicated `UD_English-GUM` genre-aware report is now published in `docs/reports/gum_genre_advanced_report_2026-03-04.json`,
- current GUM genre-aware result for targeted higher-register genres (`academic`, `court`, `essay`, `news`, `speech`, `textbook`):
  - `B2 / passive_voice`: `346`
  - `B2 / past_perfect`: `16`
  - `C1 / modal_perfect`: `1`
  - `C2 / future_perfect`: `0`
- interpretation:
  - genre-aware `GUM` materially strengthens `B2`,
  - but it does **not** solve the remaining `C1/C2` scarcity problem,
  - therefore more generic `GUM` slicing is not the right next lever for `C1/C2`.
- bounded `PMC OA` probes are now implemented and recorded in:
  - `docs/reports/pmc_oa_sample_probe_2026-03-04.json`
  - `docs/reports/pmc_oa_advanced_probe_2026-03-04.json`
  - `docs/reports/pmc_oa_advanced_dataset_probe_2026-03-04.json`
  - `docs/reports/pmc_oa_advanced_full_small_incr_2026-03-04.json`
  - `docs/reports/pmc_oa_advanced_targeted_small_incr_2026-03-04.json`
- current `PMC OA` conclusion from real bounded runs:
  - scientific prose does contribute additional `B2 / past_perfect`,
  - but it does **not** materially improve `C1 / modal_perfect` or `C2 / future_perfect`,
  - so `PMC OA` remains useful as a formal-prose support source, not as the primary path for closing `C1/C2`.
- updated next-step decision:
  - the primary next corpus source for `C1/C2` is `Project Gutenberg`,
  - specifically bounded `Essays` + `Fiction` slices with full source/provenance capture,
  - because these genres are a much better natural habitat for `should have`, `could have`, `would have`, and `will have` constructions than scientific prose.
- current `Project Gutenberg` conclusion from real bounded parser-backed runs:
  - `modal_perfect / C1` is now strongly covered and exceeds readiness threshold,
  - `future_perfect / C2` improved materially but is still below threshold,
  - latest merged readiness report shows:
    - `C1 / modal_perfect`: `1490` train support, ready
    - `C2 / future_perfect`: `36 / 50` train support, not ready yet
- current project-level conclusion:
  - the advanced ladder is **not** ready for full-ladder retrain,
  - `B2` can already be trusted structurally,
  - `C1` can now be trusted structurally,
  - `C2` still requires targeted corpus expansion before DeBERTa full-ladder training is allowed.
- next required step: increase rare advanced-pattern coverage for `future_perfect / C2` by at least `14` more train examples, then rerun advanced support gates before full-ladder retrain.

As with UD, both `OANC` and `MASC` still require:
- grammar extraction,
- CEFR rung assignment,
- note blueprint generation,
- hard ambiguity/support gates before training.

### 4.2 spaCy enrichment at scale

For every example, persist enriched features:
- token/lemma/POS/morph
- dependency + head
- phrase spans and TAM-oriented derived features

Output layers:
- `kb_raw`
- `kb_spacy_enriched`
- `kb_train_ready`

### 4.3 Phase 1 acceptance gates for rebuilt dataset

Before any DeBERTa retraining, the rebuilt Phase 1 dataset must pass hard dataset gates:

1. **Grammar-combo ambiguity gate**
- reject dataset when the same normalized grammar combo appears across multiple CEFR levels above threshold

2. **Exact-text collision gate**
- reject dataset when the same sentence text appears across multiple CEFR levels above threshold

3. **Per-class support gate**
- reject dataset when accepted grammar classes do not have enough examples per CEFR rung

4. **Evidence completeness gate**
- reject dataset when accepted rows have empty or partial grammar evidence

5. **Blueprint completeness gate**
- reject dataset when any accepted row lacks the required note blueprint payload

These gates exist specifically to prevent another classifier collapse caused by structurally non-identifiable supervision.

## 5. Quality Loop with Step Repetition

Pipeline is iterative, not one-shot:

`Generate -> Enrich -> Train -> Eval -> Diagnose -> Repair -> Repeat`

Each stage has hard quality gates.  
If a gate fails, repeat only the required stage (or previous stage), not the full run.

Implementation note:
- iterative loop runner is implemented in `ela_pipeline/classifier/iterative_loop.py`
- stopping criterion: required consecutive full-pass runs (`required_consecutive_passes`, default `3`)
- gate-level retry execution/telemetry is implemented in `ela_pipeline/classifier/quality_loop.py`
- executable quality-cycle CLI:
  - `python -m ela_pipeline.classifier.run_quality_cycle --output-dir artifacts/classifier_quality --run-id <run_id>`
  - outputs:
    - `quality_events.jsonl`
    - `repair_actions.jsonl`
    - `quality_summary.json`
- executable one-button orchestrator CLI:
  - `python -m ela_pipeline.classifier.run_full_orchestrator --run-id <run_id> --device cuda`
  - stage chain:
    - `build_kb -> build_train_dataset -> train_deberta -> run_quality_cycle`
  - output:
    - `artifacts/classifier_orchestrator/orchestrator_summary.json`

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
- blueprint traceability (rendered note preserves blueprint intent)
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
