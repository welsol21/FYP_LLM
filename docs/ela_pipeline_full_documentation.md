# ELA Pipeline: Full Documentation

## 1. Purpose
`ELA Pipeline` builds contract-compliant hierarchical linguistic JSON for English text.

End-to-end flow:
1. spaCy parsing
2. deterministic skeleton building
3. TAM enrichment (rule-based)
4. optional local T5 note generation
5. optional multilingual translation enrichment
6. validation (schema + frozen structure)
7. optional PostgreSQL persistence of final contract

Runtime policy additions:
8. runtime capability gate (`offline` / `online`)
9. media routing policy (`local` / `backend` / `reject`) by duration+size limits

Authoritative compatibility contract: `docs/sample.json`.
Tool/model/data license registry: `docs/licenses_inventory.md`.

## 2. Contract Model

### 2.1 Top-level
- JSON object keyed by sentence text.
- Each value is a `Sentence` node with `content` equal to the top-level key.

### 2.2 Node Types
Allowed types only:
- `Sentence`
- `Phrase`
- `Word`

### 2.3 Required Fields (all nodes)
- `type`
- `content`
- `tense`
- `linguistic_notes`
- `part_of_speech`
- `linguistic_elements`

### 2.4 Optional v2 Fields
- `aspect`, `mood`, `voice`, `finiteness`
- `node_id`, `parent_id`
- `source_span.start`, `source_span.end`
- `grammatical_role`
- `dep_label`, `head_id` (Word)
  - `dep_label` is the original dependency label from source parse (not phrase-internal relabeling)
- `features` (normalized morphology)
- `notes` typed objects: `{text, kind, confidence, source}`
- note trace fields: `quality_flags`, `rejected_candidates`, `rejected_candidate_stats`, `reason_codes`
- `schema_version`
- `translation` object:
  - sentence-level: `{source_lang, target_lang, model, text}`
  - node-level: `{source_lang, target_lang, text}`
- `phonetic` object: `{uk, us}`
- `synonyms` list: `[string, ...]`
- `cefr_level`: one of `A1|A2|B1|B2|C1|C2`

### 2.5 Nesting Rules
- `Sentence` can contain only `Phrase`
- `Phrase` can contain only `Word`
- `Word` must have an empty `linguistic_elements`
- serialization order rule: `linguistic_elements` is emitted as the last field in each node object (`Sentence`, `Phrase`, `Word`) for stable readability.

### 2.6 Phrase Quality Rules
- one-word phrases are disallowed
- simple determiner-led noun chunks are filtered out (for example, `the decision`)

### 2.7 Frozen Structure Rules
After skeleton creation, enrichment cannot change:
- `type`
- `content`
- `part_of_speech`
- stable graph and alignment fields when present
- children count/order and hierarchy

Only enrichment fields (notes/TAM-like metadata) may change.

### 2.8 Template Selection Trace Semantics
- `context_key_l1/l2/l3` are candidate context keys (what was attempted).
- `context_key_matched` is the effective key used for selection analytics.
- `tam_construction` remains the authoritative TAM channel even when `matched_key` is generic after `L2_DROP_TAM`.
- `quality_flags` contract:
  - `backoff_used` is required when `template_selection.level != L1_EXACT`.
  - `backoff_used` must not appear when `template_selection.level == L1_EXACT`.
  - `backoff_in_subtree` is a separate aggregate signal: `true` only when at least one descendant has local/subtree backoff.
- `matched_level_reason="tam_dropped"` is only valid for TAM-relevant nodes.
- Sentence-level backoff diagnostics:
  - `backoff_nodes_count`: count of all nodes with `backoff_used` in sentence tree (including the sentence node itself, if flagged).
  - `backoff_leaf_nodes_count`: count of non-sentence nodes with `backoff_used` (node-based, not deduplicated by span).
  - `backoff_aggregate_nodes_count`: count of aggregate backoff nodes (currently sentence-level own-node backoff only).
  - `backoff_unique_spans_count`: count of unique source spans among backoff leaf nodes.
  - Counter contract: `backoff_nodes_count = backoff_leaf_nodes_count + backoff_aggregate_nodes_count`.
  - Sentence aggregate rule: sentence is counted as aggregate backoff only when its own `template_selection.level != L1_EXACT`.
  - optional `backoff_summary` (debug mode): `nodes`, `leaf_nodes`, `aggregate_nodes_count`, `unique_spans`, `reasons`.

## 3. Validation Modes
`validate_contract` supports two modes:
- `v1`: backward-compatible baseline
- `v2_strict`: requires core v2 fields on each node (`node_id`, `source_span`, `grammatical_role`, `schema_version='v2'`)

Default mode is `v2_strict`.

Translation validation rules:
- if `translation` exists, it must be an object with non-empty `source_lang`, `target_lang`, and `text`.
- in `v2_strict`, `Sentence.translation.model` is required and must be non-empty.

CLI exposure:
```bash
python -m ela_pipeline.inference.run --validation-mode v2_strict
python -m ela_pipeline.inference.run --validation-mode v1
```

## 4. Pipeline Stages

### 4.1 Skeleton Builder (`ela_pipeline/skeleton/builder.py`)
Creates deterministic `Sentence -> Phrase -> Word` structure with POS labels, dependency metadata, and morphology features.

### 4.2 TAM Rules (`ela_pipeline/tam/rules.py`)
Detects tense/aspect/voice/mood/finiteness at sentence and phrase levels.
Example: `should have + VBN` is interpreted as past-reference perfect at phrase/sentence level.

### 4.3 Notes Generation (`ela_pipeline/annotate/local_generator.py`)
If `--model-dir` is provided:
- generates model notes
- validates quality and suitability
- applies deterministic fallback if model output is weak
- stores both legacy `linguistic_notes` and typed `notes`
- records trace fields for rejected/accepted note decisions

If `--model-dir` is omitted:
- structure and TAM are still fully produced
- notes remain empty

### 4.4 Validation (`ela_pipeline/validation/validator.py`)
- structural validity
- field type/range checks
- mode-aware strictness
- frozen structure integrity after enrichment

### 4.5 Translation Enrichment (`ela_pipeline/translate/engine.py`)
- Optional runtime stage behind CLI flag `--translate`.
- Current provider: `m2m100` (`facebook/m2m100_418M`, MIT).
- Local deployment helper: `ela_pipeline/translate/prepare_m2m100.py` saves model to `artifacts/models/m2m100_418M`.
- Runtime model resolution policy:
  - if `--translation-model` is default (`facebook/m2m100_418M`) and local `artifacts/models/m2m100_418M` exists, local directory is used;
  - explicit custom `--translation-model` value always takes priority.
- Current output fields:
  - sentence-level `translation`: `{source_lang, target_lang, model, text}`
  - node-level `translation`: `{source_lang, target_lang, text}` (when node translation is enabled)
- Node translation strategy:
  - prefer `source_span` projection from sentence text over free node content translation,
  - reuse canonical translation via `ref_node_id`,
  - deduplicate calls for identical source spans/text within sentence.

### 4.6 Phonetic Enrichment (`ela_pipeline/phonetic/engine.py`)
- Optional runtime stage behind CLI flag `--phonetic`.
- Current provider: `espeak` wrapper (`espeak-ng`/`espeak` binary in PATH).
- Ubuntu install example: `sudo apt-get update && sudo apt-get install -y --no-install-recommends espeak-ng`.
- Output field:
  - `phonetic`: `{uk, us}` on sentence and (optionally) node levels.
- Node phonetic strategy:
  - prefer `source_span` projection from sentence text over free node content,
  - reuse canonical phonetic entry via `ref_node_id`,
  - deduplicate calls for identical source spans/text within sentence.

### 4.7 Synonym Enrichment (`ela_pipeline/synonyms/engine.py`)
- Optional runtime stage behind CLI flag `--synonyms`.
- Current provider: `wordnet` (`nltk.corpus.wordnet`).
- One-time lexical data download: `.venv/bin/python -m nltk.downloader wordnet omw-1.4`.
- Output field:
  - `synonyms`: list of normalized strings (optionally attached to sentence and node levels).
- Node synonym strategy:
  - prefer `source_span` projection from sentence text over free node content,
  - reuse canonical synonyms via `ref_node_id`,
  - deduplicate by normalized source text + POS and enforce `top_k` cap,
  - return empty list for function POS (for example `auxiliary verb`, `article`, `preposition`) to avoid semantic noise; this is a valid contract outcome,
  - for content-word nodes (`noun|verb|adjective|adverb`), keep non-empty synonym lists (validator/QC enforced),
  - apply verb post-processing for context stability:
    - expand known phrasal heads (for example `bank` -> `bank on`),
    - inflect verb synonym head to node form for `past participle` contexts.

### 4.8 CEFR Enrichment (`ela_pipeline/cefr/engine.py`)
- Optional runtime stage behind CLI flag `--cefr`.
- Providers:
  - `rule`: fast deterministic baseline.
  - `t5`: local T5 model loaded from `--cefr-model-path` (GPU-only, CUDA required).
- Output field:
  - `cefr_level` on sentence and (optionally) node levels.
- Allowed CEFR labels: `A1|A2|B1|B2|C1|C2`.
- Node CEFR strategy:
  - sentence CEFR predicted from sentence content,
  - node CEFR reuses canonical prediction via `ref_node_id`,
  - duplicate source spans/text reuse cached CEFR by normalized source key.

### 4.9 PostgreSQL Persistence (`ela_pipeline/db/*`)
- Optional runtime stage behind CLI flag `--persist-db`.
- Driver: `psycopg` (PostgreSQL).
- Stores sentence-level contract snapshots in DB with deterministic `sentence_key`.
- Keying uses:
  - `canonical_text` normalization (NFC + trim + whitespace collapse),
  - `hash_version`,
  - source/target language,
  - pipeline context fingerprint.
- Current schema migration:
  - `ela_pipeline/db/migrations/0001_init.sql`
  - tables: `runs`, `sentences` (contract in `jsonb`).

### 4.10 Runtime Capability Gate (`ela_pipeline/runtime/capabilities.py`)
- Runtime mode values:
  - `online` (default)
  - `offline`
  - `auto` (resolves from `ELA_RUNTIME_MODE`, defaults to `online`)
- Deployment mode values:
  - `local`
  - `backend`
  - `distributed`
  - `auto` (resolves from `ELA_DEPLOYMENT_MODE`, defaults to `local`)
- Phonetic policy switch (license/deployment gate):
  - `ELA_PHONETIC_POLICY=enabled|disabled|backend_only`
  - `backend_only` means phonetic works only when deployment mode is `backend`.
- In `offline` mode:
  - phonetic enrichment is blocked,
  - PostgreSQL persistence is blocked,
  - backend async jobs are blocked.
- Gate behavior is fail-fast: if a blocked feature is requested, pipeline exits with explicit reason.

### 4.11 Media Routing Policy (`ela_pipeline/runtime/media_policy.py`)
- Policy inputs:
  - media duration (seconds),
  - media size (bytes),
  - env-configured limits:
    - `MEDIA_MAX_DURATION_MIN`
    - `MEDIA_MAX_SIZE_LOCAL_MB`
    - `MEDIA_MAX_SIZE_BACKEND_MB`
- Policy output:
  - `local`: process on client/runtime node,
  - `backend`: enqueue backend async job,
  - `reject`: file must not start.
- Reject reasons include actual values and configured limits for transparent UX/debug.

### 4.12 Media Orchestration + Local Queue
- Planner: `ela_pipeline/runtime/media_orchestrator.py`
  - converts routing decision into execution action:
    - `run_local`
    - `enqueue_backend`
    - `reject`
- Local queue persistence: `ela_pipeline/client_storage/sqlite_repository.py`
  - table `backend_jobs`
  - methods:
    - `enqueue_backend_job(...)`
    - `update_backend_job_status(...)`
    - `list_backend_jobs(...)`

### 4.13 Submission Entry Point (for UI Start button)
- Helper: `ela_pipeline/runtime/media_submission.py`
- Function: `submit_media_for_processing(...)`
- What it does in one call:
  1. applies media routing policy,
  2. builds execution plan (`run_local|enqueue_backend|reject`),
  3. enqueues backend job in local SQLite if backend route is required.
- Return shape (simple):
  - `route`: `local|backend|reject`
  - `status`: `accepted_local|queued_backend|rejected`
  - `message`: human-readable reason
  - `job_id`: backend queue id (only for backend route)

### 4.14 UI State Contract (for frontend integration)
- Module: `ela_pipeline/runtime/ui_state.py`
- Purpose: keep UI logic simple by sending ready-to-render payloads.
- Functions:
  - `build_runtime_ui_state(caps)`:
    - mode badge (`online|offline`)
    - feature badges (phonetic/backend jobs)
    - per-feature `enabled` flag + `reason_if_disabled`
  - `build_submission_ui_feedback(result)`:
    - maps route result to UI message payload:
      - `severity`: `info|warning|error`
      - `title`
      - `message`
- This allows frontend to render disabled states and fallback messages without duplicating runtime rules.

### 4.15 Frontend Integration Service (ready-to-use)
- Module: `ela_pipeline/runtime/service.py`
- Class: `RuntimeMediaService`
- Why it exists:
  - UI should not manually call 4-5 runtime functions for one action.
  - Service bundles capabilities, routing policy, submission, and queue access in one place.
- Main methods:
  - `get_ui_state()` -> badges + feature availability payload
  - `submit_media(...)` -> returns:
    - `result` (`route/status/message/job_id`)
    - `ui_feedback` (`severity/title/message`)
  - `list_backend_jobs(...)` -> queue list for status screens

Simple usage pattern:
1. create service once on app start,
2. call `get_ui_state()` to render mode and disabled buttons,
3. call `submit_media(...)` on Start and show `ui_feedback`.

### 4.16 Temporary Media Retention (TTL cleanup)
- Purpose: backend must not store user media permanently.
- Module: `ela_pipeline/runtime/media_retention.py`
- Config via env:
  - `MEDIA_TEMP_DIR` (default `artifacts/media_tmp`)
  - `MEDIA_RETENTION_TTL_HOURS` (default `24`)
- Behavior:
  - scans temp directory,
  - deletes files older than TTL,
  - returns cleanup report (`scanned/deleted/kept/bytes_deleted`).
- CLI command:
```bash
.venv/bin/python -m ela_pipeline.runtime.cleanup_media_tmp --dry-run
.venv/bin/python -m ela_pipeline.runtime.cleanup_media_tmp
```
- Recommended production usage:
  - run periodically via cron/systemd timer in app container/host.

### 4.17 Minimal Backend Identity Policy (phone-hash only)
- Goal: avoid storing personal data beyond minimum required account link.
- Module: `ela_pipeline/identity/policy.py`
- Rules:
  - normalize phone to strict E.164-like format (`normalize_phone_e164`),
  - compute salted hash (`hash_phone_e164`),
  - do not persist raw phone values.
- DB support:
  - migration `ela_pipeline/db/migrations/0004_backend_accounts.sql`
  - table `backend_accounts` stores only `phone_hash`.
- Repository methods:
  - `upsert_backend_account(phone_hash=...)`
  - `get_backend_account_by_phone_hash(phone_hash=...)`

### 4.18 Sync Flow for Missing Content
- Goal: if user content is missing in shared corpus, queue it for backend sync safely.
- Local queue persistence:
  - SQLite table `sync_requests` in `ela_pipeline/client_storage/sqlite_repository.py`
  - status lifecycle: `queued -> sent|failed`
- Service layer:
  - `ela_pipeline/runtime/sync_service.py` (`SyncService`)
  - methods:
    - `queue_missing_content(...)`
    - `queue_large_media_reference(...)`
    - `list_queued()`
    - `mark_sent(...)`
    - `mark_failed(...)`
- Design note:
  - queue is local-first and works offline,
  - send/retry worker can process queued requests when network is available.

### 4.19 Legacy Contract Adapter (single unified contract path)
- Module: `ela_pipeline/adapters/legacy_contract.py`
- Entry point: `adapt_legacy_contract_doc(doc)`
- Why:
  - avoid branching runtime logic for old formats,
  - normalize old payloads before validation/inference processing.
- Current adapter conversions:
  - `linguistic_notes` -> typed `notes[]` (`source="legacy"`),
  - `sentence_cefr|phrase_cefr|word_cefr` -> `cefr_level`,
  - `"null"` TAM sentinels -> real `null`,
  - missing `linguistic_elements` -> empty list,
  - missing `schema_version` -> `v2`.

### 4.20 Legacy Visualizer/Editor Bridge
- Module: `ela_pipeline/legacy_bridge/visualizer_editor.py`
- Visualizer helpers:
  - `build_visualizer_payload(sentence_node)`
  - `build_visualizer_payload_for_document(doc)`
- Editor helper:
  - `apply_node_edit(doc, sentence_text, node_id, field_path, new_value)`
- Why this matters:
  - reuse legacy visualizer/editor behavior without duplicating model logic,
  - keep edit flow on top of the same unified contract.

## 5. CLI Usage

### 5.1 Build dataset
```bash
.venv/bin/python -m ela_pipeline.dataset.build_dataset --output-dir data/processed
```
Default input is canonical `linguistic_hierarchical_3000_v5_cefr_balanced.json`.

CEFR dataset mode (same pipeline, different task):
```bash
.venv/bin/python -m ela_pipeline.dataset.build_dataset \
  --input linguistic_hierarchical_3000_v5_cefr_balanced.json \
  --task cefr_level \
  --output-dir data/processed_cefr \
  --max-per-target 0 \
  --no-dedup-exact-input-target
```

### 5.2 Train local generator
```bash
python -m ela_pipeline.training.train_generator --train data/processed/train.jsonl --dev data/processed/dev.jsonl --output-dir artifacts/models/t5_notes
```

### 5.3 Run full inference
```bash
python -m ela_pipeline.inference.run --text "She should have trusted her instincts before making the decision." --model-dir results_llm_notes_v3_t5-small_phrase/best_model
```

### 5.3.1 Runtime mode and media validation (simple)
```bash
.venv/bin/python -m ela_pipeline.inference.run \
  --text "She should have trusted her instincts before making the decision." \
  --runtime-mode offline \
  --media-duration-sec 600 \
  --media-size-bytes 157286400
```
If media is not allowed by policy, command fails immediately with a clear reason.

### 5.4 Run strict v2 inference
```bash
python -m ela_pipeline.inference.run --text "She should have trusted her instincts before making the decision." --model-dir results_llm_notes_v3_t5-small_phrase/best_model --validation-mode v2_strict
```

Note: the same command without `--validation-mode` runs in `v2_strict` by default.

### 5.5 Annotate existing JSON
```bash
python -m ela_pipeline.annotate.llm_annotator --input docs/sample.json --output inference_results/sample_with_notes.json --model-dir results_llm_notes_v3_t5-small_phrase/best_model
```

### 5.6 Translation quality regression
```bash
.venv/bin/python -m ela_pipeline.inference.translation_quality_control \
  --source-lang en \
  --target-lang ru \
  --translation-provider m2m100 \
  --translate-nodes
```

One-time local model preparation:
```bash
.venv/bin/python -m ela_pipeline.translate.prepare_m2m100
```

### 5.7 Phonetic inference (UK/US)
```bash
.venv/bin/python -m ela_pipeline.inference.run \
  --text "She should have trusted her instincts before making the decision." \
  --phonetic \
  --phonetic-provider espeak \
  --phonetic-binary auto
```

### 5.8 Phonetic quality regression
```bash
.venv/bin/python -m ela_pipeline.inference.phonetic_quality_control \
  --phonetic-provider espeak \
  --phonetic-binary auto \
  --phonetic-nodes
```

### 5.9 Synonym inference (WordNet)
```bash
.venv/bin/python -m nltk.downloader wordnet omw-1.4
.venv/bin/python -m ela_pipeline.inference.run \
  --text "She should have trusted her instincts before making the decision." \
  --synonyms \
  --synonyms-provider wordnet \
  --synonyms-top-k 5
```

### 5.10 CEFR inference
```bash
.venv/bin/python -m ela_pipeline.inference.run \
  --text "She should have trusted her instincts before making the decision." \
  --cefr \
  --cefr-provider rule
```

### 5.11 CEFR quality regression
```bash
.venv/bin/python -m ela_pipeline.inference.cefr_quality_control \
  --cefr-provider t5 \
  --cefr-model-path artifacts/models/t5_cefr/best_model \
  --cefr-nodes
```
If CUDA is unavailable, run the same command with `--cefr-provider rule` for deterministic sanity checks.

### 5.12 Inference with PostgreSQL persistence
```bash
.venv/bin/python -m ela_pipeline.inference.run \
  --text "She should have trusted her instincts before making the decision." \
  --persist-db \
  --db-url "postgresql://user:pass@localhost:5432/ela"
```
Optional flags: `--db-run-id`, `--db-source-lang`, `--db-target-lang`.

## 6. Testing
Run in activated `.venv`:
```bash
.venv/bin/python -m unittest discover -s tests -v
```

Main tested areas:
- contract validity (`docs/sample.json`)
- strict mode behavior
- frozen structure checks
- phrase quality constraints
- notes quality and fallback logic
- inference pipeline smoke tests
- translation projection and translation-contract validation

## 7. Practical Notes
1. Use `.venv` to avoid dependency mismatch.
2. If `--model-dir` path does not exist, inference raises a clear `FileNotFoundError`.
3. Use `docs/sample.json` as the canonical compatibility target.

## 8. Related Documents
- `docs/pipeline_cli.md`
- `docs/TODO.md`
- `docs/implementation_proposal.md`
- `docs/sample.json`
- `docs/TZ_ELA_Linguistic_Notes_Pipeline.docx`
