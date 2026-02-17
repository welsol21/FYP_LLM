# FYP_LLM: ELA Linguistic Notes Pipeline

## Overview
This project converts English text into a validated hierarchical linguistic JSON contract:
- `Sentence -> Phrase -> Word` structure
- deterministic parsing and rule-based enrichment
- optional local T5 note generation
- optional multilingual translation enrichment (current provider: `m2m100`, EN->RU first)
- optional phonetic enrichment (UK/US transcription via `espeak` backend)
- optional synonym enrichment (WordNet-backed, EN)
- optional CEFR enrichment (`cefr_level`, rule baseline or ML model)
- strict validation and frozen-structure checks

Authoritative contract reference: `docs/sample.json`.
Canonical CEFR corpus source: `linguistic_hierarchical_3000_v5_cefr_balanced.json`.
Tool/model/data license inventory: `docs/licenses_inventory.md`.

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
- Translation rollout completed:
  - sentence/node translation payloads
  - source-span/ref-node aware node translation projection
  - strict translation contract validation in `v2_strict`
  - translation quality regression suite (`ela_pipeline.inference.translation_quality_control`)
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
- `translation` payloads (sentence + optional node level)
- `phonetic` payloads (sentence + optional node level): `{uk, us}`
- `synonyms` payloads (sentence + optional node level): `[string, ...]`
  - synonym output applies context filters for function words; empty list is valid for function-word nodes, while content words should keep non-empty synonym sets.
  - basic verb-form normalization is applied for better contextual fit.
- `cefr_level` payload (sentence + optional node level): one of `A1|A2|B1|B2|C1|C2`

## Quick Start

### 1) Environment setup
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Docker (PostgreSQL + app)
```bash
cp .env.example .env
docker compose up -d --build
docker compose exec app python -m ela_pipeline.inference.run \
  --text "She should have trusted her instincts before making the decision." \
  --persist-db
```

Frontend is served in a separate container:
- `http://localhost:8080` (or custom `${FRONTEND_PORT}` from `.env`).

App container runs DB migrations on startup (`python -m ela_pipeline.db.migrate`).
Docker profile is CPU-only for `torch` by default (faster/lighter image build).

### 2) Run tests
```bash
.venv/bin/python -m unittest discover -s tests -v
```

### 3) Inference without generator
```bash
.venv/bin/python -m ela_pipeline.inference.run --text "She should have trusted her instincts before making the decision."
```

### 4) Inference with local model
```bash
.venv/bin/python -m ela_pipeline.inference.run \
  --text "The young scientist in the white coat carefully examined the strange artifact on the table." \
  --model-dir results_llm_notes_v3_t5-small_phrase/best_model
```

`v2_strict` is the default validation mode.

### 5) Legacy v1 compatibility mode (optional)
```bash
.venv/bin/python -m ela_pipeline.inference.run \
  --text "She should have trusted her instincts before making the decision." \
  --model-dir results_llm_notes_v3_t5-small_phrase/best_model \
  --validation-mode v1
```

### 6) Prepare local translation model (one-time)
```bash
.venv/bin/python -m ela_pipeline.translate.prepare_m2m100
```

Model files are saved into `artifacts/models/m2m100_418M`. When this path exists, inference uses it automatically for default translation settings.

### 7) Inference with translation (EN->RU)
```bash
.venv/bin/python -m ela_pipeline.inference.run \
  --text "She should have trusted her instincts before making the decision." \
  --translate \
  --translation-provider m2m100 \
  --translation-source-lang en \
  --translation-target-lang ru
```

### 8) Inference with phonetic transcription (EN UK/US)
Requires `espeak-ng` or `espeak` available in PATH.
Ubuntu quick install:
```bash
sudo apt-get update && sudo apt-get install -y --no-install-recommends espeak-ng
```

```bash
.venv/bin/python -m ela_pipeline.inference.run \
  --text "She should have trusted her instincts before making the decision." \
  --phonetic \
  --phonetic-provider espeak
```

Sentence-only phonetics:
```bash
.venv/bin/python -m ela_pipeline.inference.run \
  --text "She should have trusted her instincts before making the decision." \
  --phonetic \
  --no-phonetic-nodes
```

### 9) Run phonetic quality regression (EN UK/US)
```bash
.venv/bin/python -m ela_pipeline.inference.phonetic_quality_control \
  --phonetic-provider espeak \
  --phonetic-binary auto \
  --phonetic-nodes
```

### 10) Inference with synonyms (EN)
WordNet prerequisite (one-time):
```bash
.venv/bin/python -m nltk.downloader wordnet omw-1.4
```

```bash
.venv/bin/python -m ela_pipeline.inference.run \
  --text "She should have trusted her instincts before making the decision." \
  --synonyms \
  --synonyms-provider wordnet \
  --synonyms-top-k 5
```

Sentence-only synonyms:
```bash
.venv/bin/python -m ela_pipeline.inference.run \
  --text "She should have trusted her instincts before making the decision." \
  --synonyms \
  --no-synonym-nodes
```

### 11) Inference with CEFR levels
Rule-based baseline:
```bash
.venv/bin/python -m ela_pipeline.inference.run \
  --text "She should have trusted her instincts before making the decision." \
  --cefr \
  --cefr-provider rule
```

ML mode (requires model artifact):
```bash
.venv/bin/python -m ela_pipeline.inference.run \
  --text "She should have trusted her instincts before making the decision." \
  --cefr \
  --cefr-provider t5 \
  --cefr-model-path artifacts/models/t5_cefr/best_model
```
Note: CEFR T5 inference follows GPU-only policy (CUDA required, no CPU fallback).

### 12) Run CEFR quality regression
```bash
.venv/bin/python -m ela_pipeline.inference.cefr_quality_control \
  --cefr-provider t5 \
  --cefr-model-path artifacts/models/t5_cefr/best_model \
  --cefr-nodes
```
If CUDA is unavailable, use `--cefr-provider rule` for a structural sanity pass.

### 13) Persist inference result to PostgreSQL
```bash
.venv/bin/python -m ela_pipeline.inference.run \
  --text "She should have trusted her instincts before making the decision." \
  --persist-db \
  --db-url "postgresql://user:pass@localhost:5432/ela"
```

## Main Commands

### Build dataset splits
```bash
.venv/bin/python -m ela_pipeline.dataset.build_dataset \
  --output-dir data/processed
```

### Build CEFR dataset splits from hierarchical corpus
```bash
.venv/bin/python -m ela_pipeline.dataset.build_dataset \
  --input linguistic_hierarchical_3000_v5_cefr_balanced.json \
  --task cefr_level \
  --output-dir data/processed_cefr \
  --max-per-target 0 \
  --no-dedup-exact-input-target
```

### Train local generator
```bash
.venv/bin/python -m ela_pipeline.training.train_generator \
  --train data/processed/train.jsonl \
  --dev data/processed/dev.jsonl \
  --output-dir artifacts/models/t5_notes
```

Optional feedback mix-in:

```bash
.venv/bin/python -m ela_pipeline.training.train_generator \
  --train data/processed/train.jsonl \
  --dev data/processed/dev.jsonl \
  --feedback-train data/feedback/train.jsonl \
  --feedback-weight 2 \
  --output-dir artifacts/models/t5_notes
```

### Build skeleton and apply TAM from JSONL
```bash
.venv/bin/python -m ela_pipeline.build_skeleton --input input.jsonl --output skeleton.jsonl
.venv/bin/python -m ela_pipeline.run_tam --input skeleton.jsonl --output tam.jsonl
```

### Run translation quality regression (EN->RU)
```bash
.venv/bin/python -m ela_pipeline.inference.translation_quality_control \
  --source-lang en \
  --target-lang ru \
  --translation-provider m2m100 \
  --translate-nodes
```

## Documentation
- Full documentation: `docs/ela_pipeline_full_documentation.md`
- CLI usage: `docs/pipeline_cli.md`
- License inventory: `docs/licenses_inventory.md`
- DB persistence: `docs/db_persistence.md`
- Docker deployment: `docs/deploy_docker.md`
- Implementation proposal: `docs/implementation_proposal.md`
- Progress TODO: `docs/TODO.md`
- Curator summary report: `docs/curator_progress_report.md`
- Technical specification: `docs/TZ_ELA_Linguistic_Notes_Pipeline.docx`
