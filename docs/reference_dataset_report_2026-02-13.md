# Reference-Based Dataset Iteration Report (2026-02-13)

## What was implemented
- Added deterministic reference-template target generation mode in `ela_pipeline/dataset/build_dataset.py` via `--use-reference-templates`.
- Added POS and dependency role normalization maps and template variants for `Sentence`, `Phrase`, and `Word` levels.
- Added test coverage for reference-template mode in `tests/test_build_dataset.py`.

## Dataset build result
Command:
- `python -m ela_pipeline.dataset.build_dataset --input linguistic_hierarchical_3000_v3.json --output-dir data/processed_reference --max-per-target 40 --dedup-exact-input-target --balance-level-tam --use-reference-templates`

Key stats (`data/processed_reference/stats.json`):
- `total_before_dedup`: 30981
- `total_after_dedup`: 708
- `unique_targets` after dedup: 110
- `duplicate_ratio` after dedup: 0.844633

Compared to current refreshed dataset (`data/processed/stats.json`):
- unique targets improved: `61 -> 110`
- duplicate ratio improved: `0.910949 -> 0.844633`

## Training + evaluation
- Trained model: `results_llm_notes_reference_templates_e2`
- Eval: `eval_loss=0.5337145328521729`, `eval_exact_match=0.0`

## Regression comparison
File: `docs/inference_regression_reference_vs_current_2026-02-13.json`

- Current refreshed model (`results_llm_notes_refresh_data_processed_e2/best_model`):
  - accepted note rate: `0.0`
  - fallback rate: `1.0`
  - rejected nodes total: `1`

- Reference-template model (`results_llm_notes_reference_templates_e2/best_model`):
  - accepted note rate: `0.0`
  - fallback rate: `1.0`
  - rejected nodes total: `1`

## Conclusion
- Reference-template mode improved dataset diversity/quality metrics.
- On this probe suite, note acceptance did not improve yet (fallback remained dominant).
- Next step should combine: (1) reference templates, (2) stronger target balancing/anti-collapse constraints, and (3) larger training corpus to move acceptance rate.
