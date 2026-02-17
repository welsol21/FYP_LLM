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
- media submit form + route/status feedback (`local|backend|reject`),
- backend jobs table,
- visualizer tree rendering,
- minimal node edit action (apply edit + re-render),
- frontend API abstraction (`RuntimeApi`) with mock implementation for local development,
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

Replace `MockRuntimeApi` with production transport adapter (HTTP/CLI bridge) mapped to runtime commands:
- `ui-state`
- `submit-media`
- `backend-jobs`
- `visualizer-payload`
- `apply-edit`
