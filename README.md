# ELA — English Language Assistant

**FYP Implementation — Vladyslav Rastvorov, MTU Cork, BSc Software Development, 2025–2026**
Supervised by Dr. Alex Vakaloudis (research) and Dr. Nasir Ahmad (implementation).

ELA converts English text, audio, and video into a validated hierarchical linguistic JSON contract
(`Sentence → Phrase → Word`), enriched with grammar annotations, CEFR difficulty levels,
EN→RU translations, and IPA phonetics. A React/PWA frontend renders the contract as an
interactive tree and produces bilingual subtitle videos and audio artifacts.

Live deployment: **el-a.uk** · Thesis source: [welsol21/FYP_report](https://github.com/welsol21/FYP_report)

---

## Table of Contents

1. [Architecture](#architecture)
2. [Project Structure](#project-structure)
3. [Quick Start (Docker)](#quick-start-docker)
4. [Environment Variables](#environment-variables)
5. [Backend Pipeline](#backend-pipeline)
6. [CLI Reference](#cli-reference)
7. [Frontend](#frontend)
8. [Database](#database)
9. [Running Tests](#running-tests)
10. [Deployment](#deployment)
11. [Contract Format](#contract-format)
12. [Documentation](#documentation)

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│  Browser / PWA                                  │
│  React 18 + TypeScript + Vite                   │
│  SQLite (sql.js) — offline project storage      │
└───────────────────┬─────────────────────────────┘
                    │ HTTP  /api/*
┌───────────────────▼─────────────────────────────┐
│  ela_pipeline.runtime.api_server  :8000         │
│  ├── POST /api/sentence_contract                │
│  ├── POST /api/analyze_media  (async job)       │
│  ├── GET  /api/job_status                       │
│  └── POST /api/render_media                     │
└───────────────────┬─────────────────────────────┘
                    │
┌───────────────────▼─────────────────────────────┐
│  ela_pipeline core                              │
│  spaCy → skeleton → TAM → T5 notes → enrichment│
└───────────────────┬─────────────────────────────┘
                    │
      PostgreSQL / SQLite (analysis history)
```

| Service | Port | Description |
|---|---|---|
| `ela-app` | 8000 | Python API + pipeline |
| `ela-frontend` | 8080 | React SPA served by nginx |
| `ela-postgres` | — (internal) | PostgreSQL 16 |

---

## Project Structure

```
FYP_LLM/
├── ela_pipeline/
│   ├── parse/           # spaCy parser wrapper
│   ├── skeleton/        # Sentence → Phrase → Word builder
│   ├── tam/             # Tense / Aspect / Mood / Voice rules
│   ├── annotate/        # T5 notes generator + template fallback
│   ├── classifier/      # CEFR & grammar classifiers (DeBERTa, tabular)
│   ├── translate/       # M2M100 multilingual translation
│   ├── phonetic/        # espeak-ng IPA transcription
│   ├── synonyms/        # WordNet synonym extraction
│   ├── cefr/            # CEFR level prediction (rule-based + ML)
│   ├── inference/       # Main entry points (run.py, quality control)
│   ├── runtime/         # HTTP API server, media pipeline, service layer
│   ├── validation/      # Schema validation, frozen-structure checks
│   ├── db/              # SQLAlchemy ORM, SQL migrations
│   ├── client_storage/  # Frontend project/file metadata (SQLite)
│   ├── dataset/         # Dataset builders for training
│   └── training/        # T5 fine-tuning pipeline
│
├── frontend/
│   ├── src/
│   │   ├── pages/       # Route-level pages
│   │   ├── components/  # Shared UI components
│   │   ├── api/         # HTTP client + TypeScript types
│   │   ├── lib/         # LocalStorage, PWA, diagnostics
│   │   └── workers/     # Web Workers (Whisper ASR, translation)
│   ├── public/          # Static assets (FFmpeg WASM, ONNX models)
│   ├── src-tauri/       # Tauri desktop wrapper (in development, branch: tauri_app)
│   ├── Dockerfile       # Multi-stage: Node build → nginx
│   └── nginx.conf
│
├── artifacts/           # Pre-trained models + cached outputs
│   ├── models/
│   │   ├── m2m100_418M/             # M2M100 translation
│   │   ├── t5_cefr/                 # T5-based CEFR classifier
│   │   └── deberta_classifier_cefr/ # DeBERTa grammar classifier
│   └── media_contracts/             # Cached analysis outputs
│
├── data/                # Training & evaluation datasets
├── docs/                # Full documentation, thesis, specs
├── schemas/             # JSON schema definitions
├── tests/               # Unit and integration tests
├── temp/                # Archived training scripts and datasets
│
├── docker-compose.yml
├── Dockerfile
├── requirements-docker-cpu.txt   # Production dependencies (CPU torch)
├── requirements.txt              # Dev dependencies (includes torch, pytest)
└── .env.example
```

---

## Quick Start (Docker)

```bash
git clone <repo> && cd FYP_LLM
cp .env.example .env
docker compose up -d --build

# Frontend: http://localhost:8080
# API:      http://localhost:8000
```

Rebuild only the frontend (always use `--no-cache`):

```bash
docker compose build --no-cache frontend && docker compose up -d
```

Run a single inference inside the app container:

```bash
docker compose exec app python -m ela_pipeline.inference.run \
  --text "She should have trusted her instincts before making the decision." \
  --persist-db
```

---

## Environment Variables

Key variables — full list in `.env.example`.

| Variable | Default | Description |
|---|---|---|
| `ELA_DB_BACKEND` | `sqlite` | `sqlite` or `postgresql` |
| `ELA_DATABASE_URL` | — | PostgreSQL connection string |
| `FRONTEND_PORT` | `8080` | Host port for the frontend |
| `ELA_RUNTIME_MODE` | `online` | `online` (full features) or `offline` |
| `ELA_MEDIA_ASR_MODEL` | `base` | Whisper model: `base`, `small`, `medium`, `large` |
| `ELA_SENTENCE_NOTES_USE_CHATGPT` | `0` | `1` to use OpenAI GPT for notes |
| `OPENAI_API_KEY` | — | Required only if ChatGPT notes enabled |
| `LARA_CLIENT_ID` / `LARA_CLIENT_SECRET` | — | Lara translation provider |
| `DEEPL_API_KEY` | — | DeepL translation provider |
| `MEDIA_MAX_DURATION_MIN` | `15` | Max media duration (minutes) |
| `MEDIA_RETENTION_TTL_HOURS` | `24` | Temp file TTL |

### Sentence Notes Policy

- Default: deterministic rule-based notes (`ela_pipeline/runtime/sentence_notes.py`).
- ChatGPT: disabled by default; requires `ELA_SENTENCE_NOTES_USE_CHATGPT=1` **and** `OPENAI_API_KEY`.
- If ChatGPT output fails quality checks, runtime falls back to deterministic notes automatically.

---

## Backend Pipeline

### Processing Flow

```
Input text / audio / video
    │
    ├─[audio/video]─► Whisper ASR → transcript
    │
    ▼
spaCy parser          tokenisation, POS, dependency parse
    ▼
Skeleton builder      Sentence → Phrase → Word hierarchy
                      assigns part_of_speech, source_span, node_id
    ▼
TAM enrichment        rule-based tense / aspect / mood / voice / finiteness
    ▼
Linguistic notes      local T5 model + template fallback  (opt: ChatGPT)
    ▼
Enrichments           translation · phonetics · synonyms · CEFR
                      (each independently toggled)
    ▼
Schema validation     v2_strict contract validation
    ▼
Persistence           SQLite or PostgreSQL
    ▼
JSON contract output + media artifacts
```

### Key Modules

| Module | Purpose |
|---|---|
| `skeleton/builder.py` | Deterministic Sentence→Phrase→Word structure from spaCy doc. Frozen after build — no downstream stage may add/remove nodes. |
| `tam/rules.py` | Rule-based tense, aspect, mood, voice, finiteness detection. |
| `annotate/local_generator.py` | Fine-tuned T5 model for pedagogical notes. Falls back to template registry on quality failure. Four modes: `template_only`, `llm`, `hybrid`, `two_stage`. |
| `translate/` | Pluggable provider system: M2M100 (local), Lara, DeepL, OpenAI. Per-node translation cached in contract. |
| `runtime/api_server.py` | `ThreadingHTTPServer` on port 8000. Async job queue for long-running media processing. |
| `runtime/media_pipeline.py` | Whisper ASR → per-sentence contract → ffmpeg video render with bilingual subtitles and TTS voiceover. |
| `validation/` | RLE v2 / v2_strict schema validation + frozen-structure checks. |

### Backend truth-layer design

- `spaCy + rules` — structural grammar fields, `grammar_classes`, TAM.
- `tabular ML` — `cefr_level` (production default).
- `T5` — human-facing note wording only.
- `DeBERTa` — research/benchmark path; not a production dependency.
- `Qwen2.5-7B-Instruct` — candidate for future notes experiments; not in production.

---

## CLI Reference

### Basic inference

```bash
# No enrichments
python -m ela_pipeline.inference.run \
  --text "She should have trusted her instincts before making the decision."

# With local T5 notes model
python -m ela_pipeline.inference.run \
  --text "..." \
  --model-dir results_llm_notes_v3_t5-small_phrase/best_model

# v1 backward-compatible mode
python -m ela_pipeline.inference.run \
  --text "..." \
  --validation-mode v1
```

### Translation (EN→RU)

```bash
# One-time model download
python -m ela_pipeline.translate.prepare_m2m100
# Model saved to artifacts/models/m2m100_418M — used automatically thereafter.

python -m ela_pipeline.inference.run \
  --text "..." \
  --translate \
  --translation-provider m2m100 \
  --translation-source-lang en \
  --translation-target-lang ru
```

### Phonetics

```bash
# Install espeak-ng (Ubuntu)
sudo apt-get install -y --no-install-recommends espeak-ng

# All nodes
python -m ela_pipeline.inference.run --text "..." --phonetic --phonetic-provider espeak

# Sentence level only
python -m ela_pipeline.inference.run --text "..." --phonetic --no-phonetic-nodes

# Quality regression
python -m ela_pipeline.inference.phonetic_quality_control \
  --phonetic-provider espeak --phonetic-nodes
```

### Synonyms

```bash
# One-time WordNet download
python -m nltk.downloader wordnet omw-1.4

python -m ela_pipeline.inference.run \
  --text "..." --synonyms --synonyms-provider wordnet --synonyms-top-k 5

# Sentence level only
python -m ela_pipeline.inference.run --text "..." --synonyms --no-synonym-nodes
```

### CEFR

```bash
# Rule-based (no model required)
python -m ela_pipeline.inference.run --text "..." --cefr --cefr-provider rule

# ML mode (CUDA required)
python -m ela_pipeline.inference.run \
  --text "..." --cefr --cefr-provider t5 \
  --cefr-model-path artifacts/models/t5_cefr/best_model

# Quality regression
python -m ela_pipeline.inference.cefr_quality_control \
  --cefr-provider t5 --cefr-model-path artifacts/models/t5_cefr/best_model --cefr-nodes
```

### Persist to database

```bash
python -m ela_pipeline.inference.run \
  --text "..." \
  --persist-db \
  --db-url "postgresql://user:pass@localhost:5432/ela"
```

### Full enrichment (all flags)

```bash
python -m ela_pipeline.inference.run \
  --text "She should have trusted her instincts before making the decision." \
  --model-dir results_llm_notes_v3_t5-small_phrase/best_model \
  --translate --translation-provider m2m100 \
  --phonetic --phonetic-provider espeak \
  --synonyms --synonyms-provider wordnet \
  --cefr --cefr-provider rule \
  --persist-db
```

### Translation quality regression

```bash
python -m ela_pipeline.inference.translation_quality_control \
  --source-lang en --target-lang ru \
  --translation-provider m2m100 --translate-nodes
```

### Dataset and training

```bash
# Build dataset splits
python -m ela_pipeline.dataset.build_dataset --output-dir data/processed

# Build CEFR dataset splits
python -m ela_pipeline.dataset.build_dataset \
  --task cefr_level --output-dir data/processed_cefr \
  --max-per-target 0 --no-dedup-exact-input-target

# Train T5 notes generator
python -m ela_pipeline.training.train_generator \
  --train data/processed/train.jsonl \
  --dev data/processed/dev.jsonl \
  --output-dir artifacts/models/t5_notes

# With feedback mix-in
python -m ela_pipeline.training.train_generator \
  --train data/processed/train.jsonl \
  --dev data/processed/dev.jsonl \
  --feedback-train data/feedback/train.jsonl \
  --feedback-weight 2 \
  --output-dir artifacts/models/t5_notes
```

### Classifier pipeline (DeBERTa, CUDA required)

```bash
# Step-by-step
python -m ela_pipeline.classifier.build_kb \
  --output-dir artifacts/classifier_kb --spacy-model en_core_web_sm

python -m ela_pipeline.classifier.build_train_dataset \
  --input-path artifacts/classifier_kb/kb_spacy_enriched.jsonl \
  --output-dir data/processed_classifier

python -m ela_pipeline.classifier.train_deberta_classifier \
  --train-path data/processed_classifier/train_classifier.jsonl \
  --dev-path data/processed_classifier/dev_classifier.jsonl \
  --output-dir artifacts/models/deberta_classifier_cefr \
  --device cuda

python -m ela_pipeline.classifier.run_quality_cycle \
  --output-dir artifacts/classifier_quality \
  --run-id qc-$(date +%Y%m%d_%H%M%S)

# One-button orchestrator
python -m ela_pipeline.classifier.run_full_orchestrator \
  --run-id orch-$(date +%Y%m%d_%H%M%S) --device cuda
# Output: artifacts/classifier_orchestrator/orchestrator_summary.json
```

### Skeleton + TAM from JSONL

```bash
python -m ela_pipeline.build_skeleton --input input.jsonl --output skeleton.jsonl
python -m ela_pipeline.run_tam --input skeleton.jsonl --output tam.jsonl
```

---

## Frontend

**Tech stack:** React 18 · TypeScript 5 · Vite 5 · React Router v6 · Vitest

**Client-side ML:** Hugging Face Transformers.js + ONNX Runtime (Whisper, translation worker)

**Offline:** PWA with Service Worker, sql.js (SQLite) for local project storage

| Page | Route | Description |
|---|---|---|
| Media | `/` | Upload audio/video/text, start analysis |
| Analyze | `/analyze` | Direct text input |
| Analysis History | `/analyze-list` | Browse past analyses, download artifacts |
| Visualizer | `/visualizer` | Interactive grammatical tree |
| Vocabulary | `/vocabulary` | Extracted words/phrases, CEFR filter, CSV/JSON export |
| Config | `/config` | Translation providers, API keys |
| About | `/about` | Product description, usage guide, investor pitch |

**Dev server:**

```bash
cd frontend
npm install
npm run dev      # http://localhost:5173 — proxies /api/* to :8000
npm run build
npm run test
```

---

## Database

Two supported backends, switched via `ELA_DB_BACKEND`:

- **SQLite** (default) — zero-config, files in `artifacts/`.
- **PostgreSQL** — set `ELA_DATABASE_URL`; required for multi-user/cloud deployments.

Migrations run automatically on startup:

```bash
python -m ela_pipeline.db.migrate
```

| Migration | Description |
|---|---|
| `0001_init.sql` | Core sentences, contracts, analytics tables |
| `0002_sentences_analytics_columns.sql` | Backoff tracking, quality flags |
| `0003_hil_review_tables.sql` | HIL review schema |
| `0004_backend_accounts.sql` | Backend identity management |

Client-side state (frontend projects and file metadata) is stored separately in `artifacts/client_state.sqlite3`, managed by `ela_pipeline/client_storage/`.

---

## Running Tests

```bash
# Backend
pip install -r requirements.txt
python -m unittest discover -s tests -v
# or
pytest tests/ -v

# Frontend
cd frontend && npm run test
```

---

## Deployment

Production server: **el-a.uk** (Hetzner), branch `master` at `/opt/ela/`.

```bash
# 1. Merge dev → master locally and push
git checkout master && git merge dev && git push && git checkout dev

# 2. Pull and rebuild on server
ssh ela 'cd /opt/ela && git pull && docker compose build --no-cache frontend && docker compose up -d'
```

**Notes:**
- Always use `--no-cache` for the `frontend` service — Docker caches the build layers even after `git pull` without it.
- `ela-app` invalidates its layers correctly and can use a normal build.
- Reclaim Docker build cache if disk is tight: `docker builder prune -f`

---

## Contract Format

Each contract is a `Record<sentence_text, Node>` where nodes are recursive:

```jsonc
{
  "She came to him towards morning.": {
    "node_id": "n1",
    "type": "Sentence",
    "content": "She came to him towards morning.",
    "part_of_speech": "sentence",
    "source_span": { "start": 0, "end": 31 },
    "schema_version": "v2",
    "tense": "past",
    "aspect": "simple",
    "mood": "indicative",
    "voice": "active",
    "cefr_level": "A2",
    "linguistic_notes": {
      "elementary": "...",
      "intermediate": "...",
      "advanced": "..."
    },
    "translations": {
      "m2m100": { "text": "Она пришла к нему к утру.", "source_lang": "en", "target_lang": "ru" }
    },
    "phonetic": { "uk": "ʃiː keɪm...", "us": "ʃiː keɪm..." },
    "linguistic_elements": [
      {
        "node_id": "n2", "type": "Word", "content": "She",
        "part_of_speech": "pronoun", "cefr_level": "A1",
        "source_span": { "start": 0, "end": 3 },
        "dep_label": "nsubj", "head_id": "n3",
        "linguistic_elements": []
      },
      {
        "node_id": "n3", "type": "Phrase", "content": "came to him towards morning",
        "part_of_speech": "verb phrase",
        "source_span": { "start": 4, "end": 31 },
        "linguistic_elements": [ /* nested Word nodes */ ]
      }
    ]
  }
}
```

**Schema versions:** `v1` (backward-compatible baseline) · `v2` (adds `node_id`, `source_span`, TAM fields) · `v2_strict` (production default — all v2 fields required).

**Validation modes:** `v1` (permissive, legacy) · `v2_strict` (default, enforces full contract).

---

## Documentation

| File | Description |
|---|---|
| `docs/ela_pipeline_full_documentation.md` | Full pipeline documentation (13 sections) |
| `docs/pipeline_cli.md` | Complete CLI flag reference |
| `docs/db_persistence.md` | Database schema and ORM details |
| `docs/deploy_docker.md` | Docker deployment guide |
| `docs/licenses_inventory.md` | Tool/model/data license inventory |
| `docs/contract_field_ownership_2026-03-04.md` | Field responsibility matrix |
| `docs/TODO.md` | Active work items |
| `docs/sample.json` | Authoritative contract example |
| `docs/FYP_ResearchProject_Thesis_VladyslavRastvorov_R00274535.pdf` | Full thesis |

---

*ELA — Final Year Project, Vladyslav Rastvorov, MTU Cork, 2025–2026*
