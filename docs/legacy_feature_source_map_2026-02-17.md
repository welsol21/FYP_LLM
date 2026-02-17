# Legacy Feature Source Map (Integration Baseline)

Date: 2026-02-17

Purpose: single reference of which uploaded legacy files are canonical sources for each non-model feature planned for integration.

Scope note: model-training/model-inference scripts from legacy projects are intentionally excluded.

## Canonical Source Matrix

1. UI shell and navigation baseline (`Projects -> Files -> Analyze -> Vocabulary`)
- Source project: `temp/ela.zip` (extracted as `/tmp/ela_project`)
- Source files:
  - `/tmp/ela_project/main_menu_app.py`
  - `/tmp/ela_project/main_menu.kv`
  - `/tmp/ela_project/Description_of_ui_prototype.md`
- Integration target: new frontend app flow (no redesign from scratch).

2. Analyze progress workspace pattern (pipeline stage progress bars)
- Source project: `temp/ela.zip`
- Source files:
  - `/tmp/ela_project/ui/workspace.py`
  - `/tmp/ela_project/main_menu_app.py` (class `Workspace`)
- Integration target: analyze-run screen in production UI.

3. Vocabulary screen behavior (table actions, export triggers, visualizer entrypoint)
- Source project: `temp/ela.zip`
- Source files:
  - `/tmp/ela_project/main_menu.kv` (`<Vocabulary>`)
  - `/tmp/ela_project/main_menu_app.py` (`Vocabulary`, `VocabExportModal`, `open_visualizer`)
- Integration target: vocabulary action center in new frontend.

4. Linguistic tree visualizer UI components
- Source project: `temp/linguistic-visualizer.zip` (extracted as `/tmp/linguistic-visualizer`)
- Source files:
  - `/tmp/linguistic-visualizer/src/App.jsx`
  - `/tmp/linguistic-visualizer/src/components/LinguisticNode.jsx`
  - `/tmp/linguistic-visualizer/src/components/LinguisticBlock.jsx`
  - `/tmp/linguistic-visualizer/src/components/NodeBox.jsx`
- Integration target: embedded visualizer inside Vocabulary flow.

5. Local user state persistence pattern (device-local DB approach)
- Source project: `temp/ela.zip`
- Source files:
  - `/tmp/ela_project/core/db_utils.py`
  - `/tmp/ela_project/settings.db` (prototype artifact)
  - `/tmp/ela_project/cache.db` (prototype artifact)
- Integration target: production SQLite schema for client-local workspace state.

6. Pipeline orchestration UX hooks (not model logic)
- Source project: `temp/ela.zip`
- Source files:
  - `/tmp/ela_project/core/pipeline.py`
  - `/tmp/ela_project/core/ttw.py`
- Integration target: client pipeline controls and status flow.

7. Legacy hierarchical corpus/format compatibility references
- Source project: `temp/DualingvoMachine.zip` (extracted as `/tmp/DualingvoMachine`)
- Source files:
  - `/tmp/DualingvoMachine/linguistic_hierarchical_3000_v3.json`
  - `/tmp/DualingvoMachine/dic_structure.json`
  - `/tmp/DualingvoMachine/dictionary.json`
- Integration target: ingestion adapters only (no branching runtime contracts).

## Explicitly Non-Canonical for Integration

1. Legacy duplicate/older UI variants
- `/tmp/ela_project/main_menu_app1.py`
- `/tmp/ela_project/main_menu1.kv`

2. Legacy training/inference scripts
- `/tmp/DualingvoMachine/train_*.py`
- `/tmp/DualingvoMachine/predict_*.py`
- `/tmp/DualingvoMachine/inference.py`

These remain reference-only and are not planned as direct integration sources.

## Rules

1. Any new feature imported from legacy code must be mapped in this document before implementation starts.
2. For each mapped feature, integration must preserve current unified contract and TODO-first process.
3. If a source has conflicting variants, the canonical file must be selected here first, then coded.
