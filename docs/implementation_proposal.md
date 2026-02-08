# Full Implementation Proposal for ELA Linguistic Notes Pipeline

## 1. Phase 1: Deterministic Core Pipeline (spaCy + Skeleton + TAM + Validator)

- Build modules in `src/ela_pipeline/`:
  - `corpus/normalize.py`
  - `parse/spacy_parser.py`
  - `skeleton/builder.py`
  - `tam/rules.py`
  - `validation/schema.py`
  - `validation/logical.py`
- Define strict JSON Schema in `schemas/linguistic_contract.schema.json`.
- Add CLI:
  - `python -m ela_pipeline.build_skeleton --input data/raw.jsonl --output data/skeleton.jsonl`
  - `python -m ela_pipeline.run_tam --input data/skeleton.jsonl --output data/tam.jsonl`
- Acceptance criteria:
  - identical input always produces identical structure and `content`;
  - TAM tests pass on the reference set.

## 2. Phase 2: Dataset Generation (LLM Annotator + Strict Validation)

- Add `src/ela_pipeline/annotate/llm_annotator.py` and prompt templates.
- Enforce mandatory “structure/content frozen” validation before saving.
- Implement `dataset_builder.py`:
  - `input = skeleton + TAM + metadata`
  - `target = linguistic_notes` (recommended mode A)
- Categorize errors:
  - JSON parse error
  - schema error
  - content drift
  - logical contradiction
- Outputs:
  - `data/processed/train.jsonl`, `dev.jsonl`, `test.jsonl`
  - `reports/annotation_quality.json`

## 3. Phase 3: Local Model Training and Evaluation

- Refactor current scripts (`t5_training_script.py`, `train_llm_1_linguistic_notes_base_cpu.py`, `train_llm_1_linguistic_notes_base_cuda.py`) into a single trainer:
  - `src/ela_pipeline/training/train_generator.py`
  - config `configs/train_t5_small.yaml`
- Support CPU/CUDA via flags/config.
- Add evaluation:
  - ROUGE-L, BLEU
  - rate of structurally valid outputs
  - sample export for human review
- Version artifacts:
  - `artifacts/models/<run_id>/`
  - `artifacts/metrics/<run_id>.json`

## 4. Phase 4: Production Inference Runner

- Implement chain:
  - `parse -> skeleton -> TAM -> generator -> validator -> final JSON`
- Replace flat inference output with hierarchical contract-compliant JSON.
- Add entrypoint:
  - `python -m ela_pipeline.infer --text "..." --model artifacts/models/...`
- Error handling:
  - honest fail with structured diagnostics only;
  - do not return partially broken JSON.

## Target Repository Structure

- `src/ela_pipeline/...`
- `schemas/...`
- `configs/...`
- `tests/unit/...`
- `tests/integration/...`
- `data/{raw,interim,processed}/...`
- `artifacts/{models,metrics,reports}/...`

## Acceptance Criteria (from specification)

- TAM accuracy >= 90% on 200 manually reviewed sentences.
- LLM annotation structural validation >= 99%.
- Inference JSON validity >= 99%.
- Human evaluation on 50+ sentences confirms note quality and consistency.

## Current Gap vs Specification

- Baseline generator training/inference scripts already exist.
- Missing deterministic pipeline components:
  - Skeleton Builder
  - TAM Rule Engine
  - strict Validator
  - Dataset Builder orchestration
  - production-safe end-to-end inference

## Recommended Implementation Order

1. Fully implement Phase 1 first (foundation and drift protection).
2. Build a minimal inference vertical slice (Phase 4).
3. Complete Phase 2 and Phase 3 for scalable data prep and model quality.
