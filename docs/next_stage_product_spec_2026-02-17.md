# Next Stage Product Spec (Client-First)

Date: 2026-02-17

## 1. Goal

Build a production-ready ELA app as a single coherent product from existing parts:

- current `FYP_LLM` pipeline/backend,
- reusable UI/UX patterns from `main_menu` (ELA prototype),
- useful non-model features from legacy subprojects.

The product must remain free-first, privacy-first, and usable offline after installation.

## 2. Product Principles

- Client-first processing for heavy interactive tasks.
- Lightweight backend focused on orchestration, shared corpus, and optional long jobs.
- Minimal personal data on backend.
- Offline-first user experience.
- Strict license compliance gates before enabling sensitive features in distributed mode.

## 3. UX/UI Direction (Do Not Rebuild From Scratch)

Use `main_menu` interaction model as canonical baseline and migrate it into the new frontend stack:

- shell navigation: top back + bottom sections (`Media`, `Analyze`, `Vocabulary`);
- screen flow: `Projects -> Files -> Analyze -> Vocabulary`;
- table-driven list views and row click navigation;
- pipeline workspace progress visualization;
- vocabulary action center (`Visualizer`, export, selection, review flows).

Mock + partial production UI from ELA should be refactored and reused, not redesigned from zero.

## 4. Runtime Architecture

### 4.1 Client (Primary)

- Local project/file management.
- Local pipeline run for text and short media.
- Local storage (SQLite) for user workspace state, edits, and cached outputs.
- Local visualization and human editing of key fields.

### 4.2 Backend (Secondary)

- Shared sentence/corpus knowledge base.
- Sentence-contract API only (per-sentence contract generation).
- Sync endpoint for user-submitted new content not present in shared corpus.
- Feedback/event ingestion for future quality loops.

Backend must not process media files in current architecture.

## 5. Media Processing Policy

- Client-side only for media processing in current architecture.
- Add file-size and duration limits for local path:
  - local/client path: only files within configured max size (`MEDIA_MAX_SIZE_LOCAL_MB`);
  - duration cap: configured runtime limit (current product policy: short media path only).
- Duration and size limits must be checked before job start (fail-fast with clear user message).
- Final processed media files are not stored on backend.

## 6. Privacy and Data Policy

- Avoid personal data by default.
- Backend identity: account linked to mobile phone (minimal required identifier only; store hashed/normalized form where possible).
- User learning/work artifacts should stay local-first (SQLite on device).
- Backend stores only what is needed for shared corpus and service operation.
- No permanent storage of raw or final user media on backend.

## 7. Offline/Online Mode Requirements

### Offline mode

- App works after installation without internet.
- Core pipeline and UI workflows remain available.
- Known limitations:
  - no phonetic feature if backend-only/GPL-gated provider is required;
  - media processing limited to short files (<=15 min, local capability constraints).
  - files exceeding local duration/size limits are rejected in offline mode (backend delegation is unavailable).

### Online mode

- Enables sentence-contract backend calls, shared corpus sync, and account-backed features.
- Media processing remains local; only sentence-contract requests use backend.
- Must degrade gracefully to offline behavior when network is absent.

## 8. Licensing Constraints

- Keep existing license gates for phonetic stack.
- Do not enable distributed phonetic feature path until legal gate is explicitly passed.
- Surface feature availability by mode (offline/online, local/backend) in docs and UI.

## 9. Data/Contract Continuity

- Keep one unified contract for inference outputs.
- Keep one canonical corpus path for training/inference compatibility.
- Add legacy adapters for old formats where needed (ingest/transform), instead of branching product logic.

## 10. Implementation Order (High Level)

1. Frontend foundation using reused ELA UX patterns.
2. Client local persistence (SQLite) + project/workspace model.
3. Media policy enforcement for local-only processing (duration/size fail-fast).
4. Backend sync + sentence-contract API only (minimal and stateless).
5. Offline/online capability flags and graceful degradation.
6. License-gated feature switches (phonetics and other restricted components).
7. Human-edit capture in local DB with export path to retraining dataset.
