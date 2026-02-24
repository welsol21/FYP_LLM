# Frontend Dev (React)

Location: `frontend/`

## Purpose

Touch-first production frontend for ELA flow:
- `Projects`
- `Files`
- `Analyze`
- `Vocabulary`
- `Visualizer`

## Current status (first approximation complete)

Implemented:
- app shell with top/back navigation and bottom tabs (`Media`, `Analyze`, `Vocabulary`);
- project-first flow with persisted selected project:
  - `Projects -> Files -> Analyze`;
- file upload/registration in `Files` (project-scoped), analyzed-state in tables;
- opening Analyze from file row and opening Visualizer from analyzed items;
- local media pipeline start from Analyze;
- stage progress + logs + elapsed/estimated time;
- artifact list after pipeline completion (download actions);
- visualizer sentence stream with `Prev/Next`;
- visualizer source context near navigation:
  - current `Project`
  - current `File`;
- Quick Node Edit / Translate mutually exclusive panel behavior:
  - `Quick Node Edit` button opens edit form;
  - `Translate` button opens translation controls;
  - both forms have `Close`;
- translation provider handling in visualizer:
  - active provider as primary translation,
  - collapsed block for alternative provider translations;
- touch-friendly controls (button-based field/provider selection);
- vocabulary export:
  - JSON and CSV;
  - exports selected analyzed rows;
  - includes per-provider translation columns (`translation_<provider>`).

Removed (by current architecture decision):
- backend media jobs UI table and controls from Analyze.

## Runtime API usage

Frontend uses `RuntimeApi` abstraction:
- production HTTP transport (`/api/*`);
- mock transport for development/tests.

## Tests

Run:

```bash
cd frontend
npm run test:run
```

Main active page coverage:
- `src/pages/ProjectsPage.test.tsx`
- `src/pages/FilesPage.test.tsx`
- `src/pages/AnalyzePage.test.tsx`
- `src/pages/VocabularyPage.test.tsx`
- `src/pages/VisualizerPage.test.tsx`

## Notes

- Frontend is marked as complete in first approximation.
- Next documentation commit is dedicated to full code review alignment with actual runtime behavior.
