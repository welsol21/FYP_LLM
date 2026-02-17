# ELA Pipeline CLI

## Licensing note

- Approved multilingual translation model for current EN->RU stage: `facebook/m2m100_418M` (MIT).
- Centralized license inventory for all project tools/models/data: `docs/licenses_inventory.md`.
- Run commands with project virtualenv interpreter: `.venv/bin/python -m ...`.

## 1) Fetch raw source files

```bash
python -m ela_pipeline.dataset.fetch_raw_sources \
  --output-dir data/raw_sources \
  --ud-limit 1200 --tatoeba-limit 1200 --wikinews-limit 600
```

## 2) Build licensed ingestion corpus

```bash
python -m ela_pipeline.dataset.build_ingestion_corpus \
  --config data/source_configs/ingestion_sources_bootstrap.json \
  --output-jsonl data/raw_sources/ingested_sentences.jsonl \
  --report-json docs/reports/2026-02-13/ingestion_report_2026-02-13.json
```

## 3) Extract sentence/phrase/word nodes (3k/9k/18k)

```bash
python -m ela_pipeline.dataset.extract_ingested_nodes \
  --input-jsonl data/raw_sources/ingested_sentences.jsonl \
  --output-dir data/processed_ingested_nodes \
  --sentence-quota 3000 --phrase-quota 9000 --word-quota 18000
```

## 4) Ingestion QA report

```bash
python -m ela_pipeline.dataset.report_ingestion_quality \
  --ingested-jsonl data/raw_sources/ingested_sentences.jsonl \
  --nodes-dir data/processed_ingested_nodes \
  --output-json docs/reports/2026-02-13/ingestion_quality_report_2026-02-13.json
```

## 5) Build training dataset from ingested nodes

```bash
python -m ela_pipeline.dataset.build_dataset_from_ingested \
  --nodes-dir data/processed_ingested_nodes \
  --output-dir data/processed_from_ingested_template_id \
  --min-unique-targets 12 --max-top1-share 0.45 --min-active-template-ids 12
```

## 6) Build dataset splits (legacy hierarchical input)

```bash
.venv/bin/python -m ela_pipeline.dataset.build_dataset --output-dir data/processed
```
Default input is canonical `linguistic_hierarchical_3000_v5_cefr_balanced.json`.

CEFR-classification dataset from the same hierarchical corpus:
```bash
.venv/bin/python -m ela_pipeline.dataset.build_dataset \
  --input linguistic_hierarchical_3000_v5_cefr_balanced.json \
  --task cefr_level \
  --output-dir data/processed_cefr \
  --max-per-target 0 \
  --no-dedup-exact-input-target
```

## 7) Train local generator

```bash
python -m ela_pipeline.training.train_generator --train data/processed/train.jsonl --dev data/processed/dev.jsonl --output-dir artifacts/models/t5_notes --seed 42 --learning-rate 5e-5
```

Training writes reproducibility artifacts:
- `artifacts/models/t5_notes/training_config.json`
- `artifacts/models/t5_notes/evaluation_report.json`

Feedback-retrain regression gate (train metrics + inference QC, blocks on degradation):
```bash
python -m ela_pipeline.training.feedback_regression \
  --baseline-train-report artifacts/models/t5_baseline/evaluation_report.json \
  --candidate-train-report artifacts/models/t5_feedback/evaluation_report.json \
  --baseline-qc-report docs/reports/baseline_inference_qc.json \
  --candidate-qc-report docs/reports/feedback_inference_qc.json \
  --output docs/reports/feedback_retrain_regression.json
```

Optional hard-negative loop from rejected candidates:

```bash
python -m ela_pipeline.validation.build_hard_negatives --input inference_results/pipeline_result_latest.json --output artifacts/quality/hard_negative_patterns.json --min-count 2 --max-items 200
```

To apply these patterns during note validation, set:

```bash
export ELA_HARD_NEGATIVE_PATTERNS=artifacts/quality/hard_negative_patterns.json
```

## 8) Run production inference

```bash
python -m ela_pipeline.inference.run --text "She should have trusted her instincts before making the decision." --model-dir results_llm_notes_v3_t5-small_phrase/best_model --note-mode template_only
```

2-stage mode (model predicts `template_id`, rule engine renders note):
```bash
python -m ela_pipeline.inference.run --text "She should have trusted her instincts before making the decision." --model-dir results_llm_notes_v3_t5-small_phrase/best_model --note-mode two_stage
```

Optional debug trace for sentence-level backoff diagnostics:
```bash
python -m ela_pipeline.inference.run --text "She should have trusted her instincts before making the decision." --model-dir results_llm_notes_v3_t5-small_phrase/best_model --note-mode two_stage --backoff-debug-summary
```
This adds sentence-level `backoff_summary` (`nodes`, `leaf_nodes`, `aggregate_nodes_count`, `unique_spans`, `reasons`)
in addition to always-on counters:
`backoff_nodes_count`, `backoff_leaf_nodes_count`, `backoff_aggregate_nodes_count`, and `backoff_unique_spans_count`.
Each node also carries `backoff_in_subtree` to indicate descendant-level backoff independently of local `backoff_used`.

Optional PostgreSQL persistence for inference artifact:
```bash
.venv/bin/python -m ela_pipeline.inference.run \
  --text "She should have trusted her instincts before making the decision." \
  --persist-db \
  --db-url "postgresql://user:pass@localhost:5432/ela"
```

Optional DB identity controls:
- `--db-run-id`
- `--db-source-lang`
- `--db-target-lang`

Runtime policy mode:
- `--runtime-mode auto|offline|online` (default `auto`, resolves via `ELA_RUNTIME_MODE`, defaulting to online).
- In offline mode runtime blocks backend-dependent features (`--persist-db`) and phonetic enrichment.
- `--deployment-mode auto|local|backend|distributed` controls deployment-aware license gates.
- Phonetic gate policy is controlled by env `ELA_PHONETIC_POLICY=enabled|disabled|backend_only`.

Optional media routing validation (duration+size fail-fast checks):
```bash
.venv/bin/python -m ela_pipeline.inference.run \
  --text "She should have trusted her instincts before making the decision." \
  --runtime-mode offline \
  --media-duration-sec 600 \
  --media-size-bytes 157286400
```
Policy thresholds come from env:
- `MEDIA_MAX_DURATION_MIN`
- `MEDIA_MAX_SIZE_LOCAL_MB`
- `MEDIA_MAX_SIZE_BACKEND_MB`

Framework-agnostic JSON API for frontend integration:
```bash
.venv/bin/python -m ela_pipeline.runtime.client_api --db-path artifacts/client_state.sqlite3 ui-state
.venv/bin/python -m ela_pipeline.runtime.client_api --db-path artifacts/client_state.sqlite3 submit-media --media-path /tmp/long.mp4 --duration-sec 1800 --size-bytes 314572800
.venv/bin/python -m ela_pipeline.runtime.client_api --db-path artifacts/client_state.sqlite3 backend-jobs
.venv/bin/python -m ela_pipeline.runtime.client_api --db-path artifacts/client_state.sqlite3 queue-missing-content --source-text "New sentence not in shared corpus."
.venv/bin/python -m ela_pipeline.runtime.client_api --db-path artifacts/client_state.sqlite3 sync-queue
.venv/bin/python -m ela_pipeline.runtime.client_api --db-path artifacts/client_state.sqlite3 visualizer-payload --input-json inference_results/pipeline_result_latest.json
.venv/bin/python -m ela_pipeline.runtime.client_api --db-path artifacts/client_state.sqlite3 apply-edit --input-json inference_results/pipeline_result_latest.json --output-json inference_results/pipeline_result_edited.json --sentence-text "She trusted him." --node-id p1 --field-path notes[0].text --new-value-json "\"Updated note\""
```

Production license gate check (phonetic, GPL-sensitive):
```bash
.venv/bin/python -m ela_pipeline.runtime.license_gate \
  --feature phonetic \
  --deployment-mode distributed \
  --phonetic-policy enabled \
  --legal-approval
```

Optional multilingual translation enrichment (first pair: EN->RU, provider `m2m100`):
```bash
.venv/bin/python -m ela_pipeline.translate.prepare_m2m100
```
This saves a project-local model copy to `artifacts/models/m2m100_418M`.

Translation inference:
```bash
.venv/bin/python -m ela_pipeline.inference.run \
  --text "She should have trusted her instincts before making the decision." \
  --translate \
  --translation-provider m2m100 \
  --translation-source-lang en \
  --translation-target-lang ru
```
If `artifacts/models/m2m100_418M` exists and `--translation-model` is not overridden, it is used automatically.

Dual translation channels (optional):
```bash
.venv/bin/python -m ela_pipeline.inference.run \
  --text "She should have trusted her instincts before making the decision." \
  --translate \
  --translation-dual-channels
```
This adds:
- `translation_literary`
- `translation_idiomatic`
and keeps `translation` for backward compatibility.

Sentence-only translation (skip phrase/word node translations):
```bash
.venv/bin/python -m ela_pipeline.inference.run --text "She should have trusted her instincts before making the decision." --translate --no-translate-nodes
```

Optional translation hot-path cache:
- `ELA_TRANSLATION_CACHE_BACKEND=memory|redis` (empty disables cache)
- `ELA_TRANSLATION_CACHE_URL=redis://...` (required for `redis`)
- `ELA_TRANSLATION_CACHE_TTL_SECONDS=86400` (must be `> 0`)

Translation quality regression suite (EN->RU default):
```bash
.venv/bin/python -m ela_pipeline.inference.translation_quality_control \
  --source-lang en \
  --target-lang ru \
  --translation-provider m2m100 \
  --translate-nodes
```

Optional phonetic enrichment (EN UK/US; backend `espeak`):
System prerequisite (Ubuntu):
```bash
sudo apt-get update && sudo apt-get install -y --no-install-recommends espeak-ng
```

```bash
.venv/bin/python -m ela_pipeline.inference.run \
  --text "She should have trusted her instincts before making the decision." \
  --phonetic \
  --phonetic-provider espeak \
  --phonetic-binary auto
```

Sentence-only phonetics:
```bash
.venv/bin/python -m ela_pipeline.inference.run \
  --text "She should have trusted her instincts before making the decision." \
  --phonetic \
  --no-phonetic-nodes
```

Phonetic quality regression suite (UK/US structure checks):
```bash
.venv/bin/python -m ela_pipeline.inference.phonetic_quality_control \
  --phonetic-provider espeak \
  --phonetic-binary auto \
  --phonetic-nodes
```

Optional synonym enrichment (EN, WordNet):
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
Note: empty `synonyms: []` is valid for function-word nodes; content words are expected to have non-empty synonym lists.

Sentence-only synonyms:
```bash
.venv/bin/python -m ela_pipeline.inference.run \
  --text "She should have trusted her instincts before making the decision." \
  --synonyms \
  --no-synonym-nodes
```

Optional CEFR enrichment:
Rule baseline:
```bash
.venv/bin/python -m ela_pipeline.inference.run \
  --text "She should have trusted her instincts before making the decision." \
  --cefr \
  --cefr-provider rule
```

ML predictor (fail-fast if model file is missing):
```bash
.venv/bin/python -m ela_pipeline.inference.run \
  --text "She should have trusted her instincts before making the decision." \
  --cefr \
  --cefr-provider t5 \
  --cefr-model-path artifacts/models/t5_cefr/best_model
```
GPU-only policy: CEFR T5 inference requires CUDA; CPU fallback is disabled.

CEFR quality regression suite:
```bash
.venv/bin/python -m ela_pipeline.inference.cefr_quality_control \
  --cefr-provider t5 \
  --cefr-model-path artifacts/models/t5_cefr/best_model \
  --cefr-nodes
```
If CUDA is unavailable, use `--cefr-provider rule`.

Sentence-only CEFR:
```bash
.venv/bin/python -m ela_pipeline.inference.run \
  --text "She should have trusted her instincts before making the decision." \
  --cefr \
  --no-cefr-nodes
```

`v2_strict` is now the default mode.
Legacy compatibility mode (`v1`) is still available only when explicitly requested:

```bash
python -m ela_pipeline.inference.run --text "She should have trusted her instincts before making the decision." --model-dir results_llm_notes_v3_t5-small_phrase/best_model --validation-mode v1
```

If `--model-dir` is omitted, the pipeline still returns contract-valid JSON with deterministic fields and TAM labels but empty `linguistic_notes`.
In `v2_strict`, each node must include `node_id`, `source_span`, `grammatical_role`, and `schema_version`, and uses real JSON `null` (not string `"null"`) in nullable TAM fields.

Note: the path `artifacts/models/t5_notes/best_model` is valid only if you trained a model into `artifacts/models/t5_notes` in this workspace. If that directory does not exist, pass an existing local model directory (for example `results_llm_notes_v3_t5-small_phrase/best_model`).
