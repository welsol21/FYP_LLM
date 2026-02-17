# UI Migration Map (ELA main_menu -> Current Project)

Date: 2026-02-17

Goal: migrate existing ELA `main_menu` UX into production architecture without redesign from scratch.

## 1. Canonical UX Baseline

Source:
- `/tmp/ela_project/main_menu_app.py`
- `/tmp/ela_project/main_menu.kv`

Canonical flow to preserve:
- `Projects -> Files -> Analyze -> Vocabulary`
- top back navigation
- bottom section navigation (`Media`, `Analyze`, `Vocabulary`)

## 2. Screen-by-Screen Mapping

1. Projects
- Legacy behavior: list projects, open project files, create new project.
- Target route: `projects.list`
- Data source: local SQLite (`projects` table) as primary; optional backend sync metadata.
- Actions:
  - open selected project -> `files.list`
  - create project -> local insert + UI refresh

2. Files (Project scope)
- Legacy behavior: show files for selected project, open file details/analyze, add new file.
- Target route: `projects/:projectId/files`
- Data source: local SQLite (`media_files` table).
- Actions:
  - add file (with duration+size validation)
  - select file -> `analyze.detail`

3. Analyze List
- Legacy behavior: cross-project file list with analyzed status.
- Target route: `analyze.list`
- Data source: local SQLite view over projects/files + latest run status.
- Actions:
  - open run target file -> `analyze.detail`

4. Analyze Detail
- Legacy behavior: run pipeline with workspace progress bars and stage status.
- Target route: `analyze/:fileId`
- Data source:
  - local file metadata,
  - runtime pipeline job state (local first),
  - optional backend job state for large media.
- Actions:
  - start pipeline
  - show fail-fast validation errors (duration/size/feature availability)
  - display per-stage progress and output summary

5. Vocabulary
- Legacy behavior: tabular rows, select rows, export JSON/CSV, open visualizer.
- Target route: `vocabulary`
- Data source:
  - local inferred outputs (SQLite),
  - optional merged corpus references from backend.
- Actions:
  - export selected entries JSON/CSV
  - open visualizer modal/page with selected sentence/tree

6. Visualizer
- Legacy behavior: modal placeholder in Kivy app.
- Target implementation: embedded React visualizer components from:
  - `/tmp/linguistic-visualizer/src/components/LinguisticNode.jsx`
  - `/tmp/linguistic-visualizer/src/components/LinguisticBlock.jsx`
  - `/tmp/linguistic-visualizer/src/components/NodeBox.jsx`
- Route: `vocabulary/visualizer/:sentenceKey` (or modal over vocabulary page).

## 3. Shared UI Components to Keep

1. Table pattern
- Header + scrollable body + clickable row.
- Used by Projects, Files, AnalyzeList, Vocabulary.

2. Workspace progress component
- Stage bars: loading, transcribing, translating, generating, exporting.
- Add two job modes: local and backend async.

3. Action bar pattern
- Right-side grouped buttons for screen-level actions (create/export/open visualizer).

## 4. State and Storage Mapping

Local SQLite (client):
- `projects`
- `media_files`
- `pipeline_runs`
- `pipeline_outputs`
- `review_events` / `node_edits` (already aligned with HIL direction)

Backend (optional per feature):
- shared corpus/query
- async job API for large media
- sync endpoint for user-submitted new content

## 5. Validation and Runtime Guards

Apply before job start:
- `MEDIA_MAX_DURATION_MIN=15`
- `MEDIA_MAX_SIZE_LOCAL_MB=250`
- `MEDIA_MAX_SIZE_BACKEND_MB=2048`
- feature mode checks (offline/online, phonetic license gate)

Error UX:
- show actual duration, actual size, active limit, and suggested next route (local/backend/not available offline).

## 6. Implementation Sequence (UI Track)

1. Create navigation shell and routes matching canonical flow.
2. Implement shared table and workspace components.
3. Implement Projects + Files with SQLite repository.
4. Implement Analyze screens with validation guards and pipeline hooks.
5. Integrate Vocabulary actions and visualizer components.
6. Add offline/online capability badges and disabled-state messaging.

## 7. Out of Scope for This UI Migration

- model retraining changes
- CEFR model redesign
- backend media persistence beyond defined temporary retention policy
