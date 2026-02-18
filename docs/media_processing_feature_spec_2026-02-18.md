# Media Processing Feature Spec (Backend + Frontend)

Date: 2026-02-18
Status: Draft for implementation

## 1. Goal
Implement end-to-end media ingestion and analysis for:
- text files
- PDF
- audio
- video

The system must:
- preserve offline-first behavior
- keep one unified linguistic contract for analysis/visualizer
- reuse existing media pipeline assets from legacy projects where possible
- support touch-first UX and file-based navigation in Visualizer

## 2. Scope
In scope:
- media ingestion flow
- backend routing (local/backend/reject)
- extraction stage outputs and local persistence
- mapping from media sentence stream to main contract sentences
- frontend flows for file upload, processing status, and visualizer entry

Out of scope (this iteration):
- model retraining changes
- new translation provider research
- cloud storage for user media

## 3. Source Reuse Strategy
Use existing proven pipeline logic from legacy assets (`temp/ela.zip`, `temp/DualingvoMachine.zip`) as adapters, not as direct runtime scripts.

Reusable artifacts:
- segment-level sentence objects (`text_eng`, `units`, `start/end`, `text_ru`, `units_ru`)
- cache keys (`data_hash`, parameter-aware hash)
- staged processing semantics (transcribe/translate/synthesize/export)

Rule:
- keep legacy formats only at ingestion boundary
- convert to current unified contract before visualizer/editor layers

## 4. Target Architecture

### 4.1 Processing layers
1. **Media Contract Layer** (technical extraction result)
- sentence stream with timing/alignment metadata
- provider-specific fields allowed internally

2. **Main Linguistic Contract Layer** (product contract)
- current project contract (`v2`/strict policies)
- visualizer and curation operate only on this layer

3. **Bridge Layer**
- deterministic mapping between layer 1 and layer 2
- no legacy shape leaks to frontend visualizer components

### 4.2 Routing policy
Use existing runtime policy modules:
- local route for allowed duration/size
- backend route for oversized but accepted media
- reject for hard limit violations

### 4.3 Backend processing path (large media)
For media above local limits but below backend hard limits, backend processing is mandatory:
- enqueue backend job with `job_id`, `document_id`, `media_file_id`
- upload media as temporary processing object (no permanent final-media storage)
- run extraction pipeline on backend worker (`ingest -> extract -> normalize -> analyze`)
- produce:
  - media-contract sentence stream
  - main linguistic contract sentence nodes
- return result package to client sync endpoint
- client persists returned payload in local SQLite (`documents`, `media_sentences`, `contract_sentences`, `sentence_link`)
- backend temporary artifacts are deleted by TTL policy

## 5. Data Model

### 5.1 Local storage (SQLite, client-side)
Add/extend tables for analyzed documents:

- `documents`
  - `id`
  - `project_id`
  - `media_file_id`
  - `source_type` (`text|pdf|audio|video`)
  - `source_path`
  - `media_hash`
  - `status`
  - `created_at`, `updated_at`

- `document_text`
  - `document_id`
  - `full_text`
  - `text_hash`
  - `version`

- `media_sentences`
  - `document_id`
  - `sentence_idx` (navigation order)
  - `sentence_text`
  - `start_ms`, `end_ms` (nullable for text/pdf)
  - `page_no`, `char_start`, `char_end` (nullable)
  - `sentence_hash`

- `contract_sentences`
  - `document_id`
  - `sentence_hash`
  - `sentence_node_json` (main contract node)

- `sentence_link`
  - `document_id`
  - `sentence_idx`
  - `sentence_hash`

Hash-first mapping policy:
- visualizer link key is `sentence_hash`
- for repeated text, hash input includes deterministic disambiguator (for example `normalized_text + sentence_idx`)

### 5.2 Backend storage
- temporary processing artifacts only (TTL cleanup)
- no permanent user final media and no permanent full text by default
- backend job metadata is allowed (`job_id`, status, timestamps, error code/message)
- backend may keep temporary extracted text only for active job lifecycle and TTL window

## 6. Visualizer Navigation Contract

Analyzed file behavior:
- analyzed file is a file with completed media pipeline + built main contract
- user opens visualizer by double-clicking the analyzed file in Files UI

Visualizer sentence traversal:
- `Prev/Next` uses `sentence_idx` from `media_sentences`
- render payload is resolved via `sentence_hash` -> `contract_sentences`
- result: media order preserved, visualizer stays contract-native

## 7. API/Service Changes

### 7.1 Runtime/backend service
Add operations:
- `create_document_from_media(...)`
- `get_document_processing_status(document_id)`
- `get_visualizer_payload(document_id)`
- `list_document_sentences(document_id)`
- `enqueue_backend_media_job(...)`
- `get_backend_job(job_id)`
- `retry_backend_job(job_id)`
- `resume_backend_job(job_id)`
- `sync_backend_result(job_id)` (materialize backend result into local document tables)

### 7.2 Frontend API
Extend `RuntimeApi` with document-aware methods:
- `listFiles(projectId)` including `analyzed` + `document_id`
- `openVisualizer(documentId)`
- `getVisualizerPayload(documentId)`

## 8. Frontend Flow (Touch-first)

Files screen:
- analyzed files visually marked
- double tap/click on analyzed file opens visualizer for that file

Analyze screen:
- route decision feedback (`local/backend/reject`)
- stage progress (`ingest -> extract -> normalize -> analyze`)
- backend queue status with retry/resume
- backend path UX requirements:
  - persistent `job_id` display for current file
  - polling until terminal state (`completed|failed|rejected`)
  - `Retry` action for failed jobs
  - `Resume` action when app/session restarts and job is still active
  - auto-sync local document once backend job completes

Visualizer screen:
- receives only document-scoped payload
- `Prev/Next` within current document only

## 9. Implementation Plan (TDD)

Phase 1: Data and mapping foundation
1. tests for new SQLite schema and CRUD
2. tests for sentence hash generation and duplicate-safe behavior
3. tests for media->contract sentence link builder

Phase 2: Service integration
1. tests for `document_id` processing lifecycle
2. tests for `get_visualizer_payload(document_id)` contract integrity
3. tests for routing policy integration with document creation

Phase 3: Frontend integration
1. tests for Files list analyzed-state and double-click open
2. tests for document-scoped visualizer payload fetch
3. tests for `Prev/Next` sentence traversal for one document

Phase 4: End-to-end checks
1. one text sample E2E
2. one PDF sample E2E
3. one audio sample E2E (local)
4. one oversized sample route-to-backend scenario
5. backend failure + retry scenario
6. app restart + resume backend polling scenario

## 10. Acceptance Criteria
- analyzed file opens visualizer by double-click
- visualizer navigation is stable and document-local
- no legacy payload fields are required in visualizer runtime model
- media extraction outputs are persisted locally and reusable
- unified main contract remains the only curation/visualizer contract
- tests pass for mapping, persistence, routing, and UI navigation
- backend path is fully functional for oversized media:
  - queued job visible in UI
  - retry/resume works
  - completed result is synced to local SQLite and openable in visualizer

## 11. Risks and Controls

Risk: legacy payload divergence
- control: strict adapter tests + contract validation at bridge boundary

Risk: sentence alignment mismatch
- control: deterministic hash policy and sentence_idx fallback diagnostics

Risk: storage growth
- control: retention policy for temporary artifacts, configurable limits

Risk: offline inconsistency
- control: all document/core payload persistence local-first
