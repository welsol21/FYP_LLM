# Dataset + Training Refresh Report (2026-02-13)

## Dataset diagnostics (`data/processed/stats.json`)
- Source schema: `legacy_linguistic_notes`.
- Rows before dedup: `26981`.
- Rows after dedup/balance: `685`.
- Split sizes: train `549`, dev `68`, test `68`.
- Target duplication remained high after dedup: `duplicate_ratio=0.910949` (61 unique targets total).
- Quality filtering removed `4000` low-style notes.

## Retraining baseline
- Model: `t5-small`.
- Run: `results_llm_notes_refresh_data_processed_e2`.
- Eval metrics: `eval_loss=0.415588`, `eval_exact_match=0.0`.
- Report file: `results_llm_notes_refresh_data_processed_e2/evaluation_report.json`.

## Regression inference before/after (5 fixed probes)
Comparison file: `docs/inference_regression_before_after_2026-02-13.json`.

- Before (`results_llm_notes_v3_t5-small_phrase/best_model`):
  - accepted note rate: `0.043478`
  - fallback rate: `0.956522`
  - rejected nodes total: `31`

- After (`results_llm_notes_refresh_data_processed_e2/best_model`):
  - accepted note rate: `0.065217`
  - fallback rate: `0.934783`
  - rejected nodes total: `0`

## Conclusion
- Refresh + new filtering stack removed diagnostic noise in rejected candidates on the probe suite.
- Note generation quality improved slightly, but fallback usage is still very high.
- Main remaining bottleneck is target diversity/quality in the training dataset.
