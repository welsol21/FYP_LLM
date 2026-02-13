# Template-ID Experiment Report (2026-02-13)

## Artifacts
- Dataset report: `docs/template_id_dataset_report_2026-02-13.md`
- Training report: `docs/template_id_training_report_2026-02-13.md`
- Regression comparison: `docs/inference_regression_template_id_vs_refresh_2026-02-13.json`

## Dataset status
- Built with `--use-template-id-targets` into `data/processed_template_id`.
- After balance:
  - total rows: `511`
  - unique targets: `10`
  - duplicate ratio: `0.980431`
- Active template IDs after balance: `10 / 19`.

## Training status
- Model: `results_llm_notes_template_id_e2/best_model`
- Eval metrics:
  - `eval_loss=0.6993013620376587`
  - `eval_exact_match=0.0`

## Regression vs refreshed baseline
Source: `docs/inference_regression_template_id_vs_refresh_2026-02-13.json`

- `results_llm_notes_refresh_data_processed_e2/best_model`
  - probe_count: `5`
  - timeouts: `0`
  - accepted_note_rate: `0.0`
  - fallback_rate: `1.0`
  - rejected_nodes_total: `2`

- `results_llm_notes_template_id_e2/best_model`
  - probe_count: `5`
  - timeouts: `0`
  - accepted_note_rate: `0.0`
  - fallback_rate: `1.0`
  - rejected_nodes_total: `5`

## Conclusion
- Template-id pipeline wiring is complete and deterministic.
- Current template-id dataset is too collapsed (low target diversity), which leads to weaker practical inference quality than refreshed baseline on probe suite.
- Next iteration should increase template coverage/variants and reduce duplicated targets before retraining.
