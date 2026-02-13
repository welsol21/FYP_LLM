# FYP_LLM: ELA Linguistic Notes Pipeline

## Overview
This project converts English text into a validated hierarchical linguistic JSON contract:
- `Sentence -> Phrase -> Word` structure
- deterministic parsing and rule-based enrichment
- optional local T5 note generation
- strict validation and frozen-structure checks

Authoritative contract reference: `docs/sample.json`.

## What Has Been Improved
- Contract v2 metadata added and validated (`node_id`, `parent_id`, `source_span`, `grammatical_role`, dependency links, morphology features).
- Verbal grammar split into explicit fields (`tense`, `aspect`, `mood`, `voice`, `finiteness`).
- Phrase quality improved:
  - one-word phrases removed
  - simple determiner-led noun chunks removed (for example, `the decision`)
- Notes quality pipeline improved:
  - typed notes (`notes[{text, kind, confidence, source}]`) alongside legacy `linguistic_notes`
  - fallback notes strengthened
  - validation trace fields added (`quality_flags`, `rejected_candidates`, `rejected_candidate_stats`, `reason_codes`)
- Dual validation modes implemented:
  - `v1` (backward-compatible)
  - `v2_strict` (core v2 fields required)

## Current Output Characteristics
Each node always keeps required contract fields and may include optional v2 fields such as:
- `schema_version`
- `node_id`, `parent_id`
- `source_span`
- `grammatical_role`
- `dep_label`, `head_id` (Word nodes)
- `features` (normalized morphology)
- `notes` (typed note objects)
- trace fields for note-generation quality

## Quick Start

### 1) Environment setup
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
  --model-dir results_llm_notes_v3_t5-small_phrase/best_model \
  --validation-mode v2_strict
```

### 5) Legacy v1 compatibility mode (optional)
```bash
python -m ela_pipeline.inference.run \
  --text "She should have trusted her instincts before making the decision." \
  --model-dir results_llm_notes_v3_t5-small_phrase/best_model \
  --validation-mode v1
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

## Documentation
- Full documentation: `docs/ela_pipeline_full_documentation.md`
- CLI usage: `docs/pipeline_cli.md`
- Implementation proposal: `docs/implementation_proposal.md`
- Progress TODO: `docs/TODO.md`
- Curator summary report: `docs/curator_progress_report.md`
- Technical specification: `docs/TZ_ELA_Linguistic_Notes_Pipeline.docx`
