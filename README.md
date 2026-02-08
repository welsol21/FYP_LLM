# FYP_LLM: ELA Linguistic Notes Pipeline

This repository contains an end-to-end pipeline for generating contract-compliant linguistic JSON from English text:
- deterministic parsing and structure building (spaCy + rules)
- rule-based TAM enrichment
- optional local T5 generation for `linguistic_notes`
- strict contract validation

Authoritative contract reference: `docs/sample.json`.

## Implemented

1. Core pipeline (`ela_pipeline`)
- `build_skeleton`
- `run_tam`
- `inference.run`
- validators (schema + frozen checks)

2. Data and training
- dataset builder: `ela_pipeline.dataset.build_dataset`
- unified trainer: `ela_pipeline.training.train_generator`

3. Docs and tests
- full guide: `docs/ela_pipeline_full_documentation.md`
- CLI quick guide: `docs/pipeline_cli.md`
- tests: `tests/`

## Quick Start

### 1) Install dependencies
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2) Run tests
```bash
python -m unittest discover -s tests -v
```

### 3) Inference without generator
```bash
python -m ela_pipeline.inference.run --text "She should have trusted her instincts before making the decision."
```

### 4) Inference with local model
```bash
python -m ela_pipeline.inference.run \
  --text "The young scientist in the white coat carefully examined the strange artifact on the table." \
  --model-dir results_llm_notes_v3_t5-small_phrase/best_model
```

## Main Commands

### Build dataset splits
```bash
python -m ela_pipeline.dataset.build_dataset \
  --input linguistic_hierarchical_3000_v3.json \
  --output-dir data/processed
```

### Train local generator
```bash
python -m ela_pipeline.training.train_generator \
  --train data/processed/train.jsonl \
  --dev data/processed/dev.jsonl \
  --output-dir artifacts/models/t5_notes
```

### Build skeleton and apply TAM from JSONL
```bash
python -m ela_pipeline.build_skeleton --input input.jsonl --output skeleton.jsonl
python -m ela_pipeline.run_tam --input skeleton.jsonl --output tam.jsonl
```

## Project Layout

- `ela_pipeline/` - pipeline source code
- `schemas/` - JSON schema files
- `data/processed/` - train/dev/test JSONL
- `inference_results/` - inference outputs
- `docs/` - documentation
- `tests/` - unit/smoke tests

## Documentation

- Full guide: `docs/ela_pipeline_full_documentation.md`
- CLI guide: `docs/pipeline_cli.md`
- Implementation plan: `docs/implementation_proposal.md`
- Technical specification: `docs/TZ_ELA_Linguistic_Notes_Pipeline.docx`
