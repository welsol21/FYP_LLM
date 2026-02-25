# Phase 1 Classifier Execution Report (A1 -> A2 -> B1)

Date: 2026-02-25  
Run id: `phase1_a1_a2_b1_prod_20260225_113010`  
Device: `cuda` (RTX 3090)

## 1. Orchestrator execution

Command:

```bash
.venv/bin/python -m ela_pipeline.classifier.run_full_orchestrator \
  --run-id phase1_a1_a2_b1_prod_20260225_113010 \
  --device cuda
```

Status: `completed`  
Total duration: `21737 ms`

Stages:

1. `build_kb` - completed (`529 ms`)
2. `build_train_dataset` - completed (`0 ms`)
3. `train_deberta` - completed (`21204 ms`)
4. `build_classifier_metadata` - completed (`0 ms`)
5. `run_quality_cycle` - completed (`1 ms`)

Primary summary artifact:

- `artifacts/classifier_orchestrator/orchestrator_summary.json`

## 2. Produced artifacts (baseline freeze for pre-Phase-2)

Model + metadata:

- `artifacts/models/deberta_classifier_cefr/model.safetensors`
- `artifacts/models/deberta_classifier_cefr/config.json`
- `artifacts/models/deberta_classifier_cefr/tokenizer.json`
- `artifacts/models/deberta_classifier_cefr/train_summary.json`
- `artifacts/models/deberta_classifier_cefr/classifier_metadata.json`

Quality:

- `artifacts/classifier_quality/quality_summary.json`
- `artifacts/classifier_quality/quality_events.jsonl`
- `artifacts/classifier_quality/repair_actions.jsonl`

Dataset/KB:

- `artifacts/classifier_kb/kb_raw.jsonl`
- `artifacts/classifier_kb/kb_spacy_enriched.jsonl`
- `data/processed_classifier/train_classifier.jsonl`
- `data/processed_classifier/dev_classifier.jsonl`
- `data/processed_classifier/classifier_dataset_stats.json`

## 3. Gate outcomes snapshot

All gate families passed in this run:

1. `kb_generation`
2. `spacy_enrichment`
3. `classifier`
4. `contract`
5. `nlg` (including `blueprint_traceability`)

Iterative quality loop:

- required consecutive passes: `3`
- recorded passes: `3`
- completed: `true`

## 4. Runtime sentence-contract E2E validation

Validation performed using produced model directory:

- `artifacts/models/deberta_classifier_cefr`

Result:

- runtime sentence-contract path resolves to classifier provider `deberta` (metadata present),
- sentence node is produced with classifier-backed `cefr_level`,
- contract contains `note_blueprints` (classifier truth),
- contract contains `generated_notes` (controlled note generation output).

## 5. Controlled T5 rewrite validation

Controlled mode validation confirmed on runtime sentence-contract call:

- `note_mode=controlled`,
- blueprint source fields preserved in `note_blueprints`,
- user-facing generated fields present in `generated_notes`,
- classifier-owned fields are not overwritten by generation stage.

## 6. Notes

- This report is the baseline freeze checkpoint before Phase 2 (`B2`) rollout.
- Training data size in this run remains small (`train=4`, `dev=2`) and is expected to be expanded in next data-growth cycles.

