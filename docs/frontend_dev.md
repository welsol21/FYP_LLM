# Frontend Dev (React)

## Purpose

React UI migration slice for ELA `main_menu` baseline:
- Projects
- Files
- Analyze
- Vocabulary
- Visualizer

Location: `frontend/`

## Current status

Implemented:
- route shell preserving legacy UX sequence,
- runtime capability badges + disabled reasons,
- real media upload (`multipart/form-data`) from Analyze screen to runtime backend,
- media submit form + route/status feedback (`local|backend|reject`),
- backend lifecycle controls in Analyze (`Check status`, `Retry`, `Resume`, auto-sync on completed),
- backend jobs table,
- visualizer tree rendering,
- minimal node edit action (apply edit + re-render),
- frontend API abstraction (`RuntimeApi`) with:
  - production HTTP transport (`/api/*`),
  - mock implementation for local development/tests,
- TDD tests (Vitest + Testing Library).

## Run locally

```bash
cd frontend
npm install
npm run dev
```

Open: `http://localhost:5173`

## Run tests

```bash
cd frontend
npm run test:run
```

Covered tests:
- `src/components/RuntimeStatusCard.test.tsx`
- `src/pages/AnalyzePage.test.tsx`
- `src/components/BackendJobsTable.test.tsx`
- `src/pages/VisualizerPage.test.tsx`

## Next step

Integrate ASR for direct audio/video transcription in media pipeline.
Current implementation supports:
- `text` extraction (native text read),
- `pdf` extraction (`pypdf`),
- `audio/video` via sidecar transcript file (`<media>.<ext>.txt`).
