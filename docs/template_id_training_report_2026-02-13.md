# Template-ID Training Report (2026-02-13)

## Training run

```bash
source .venv/bin/activate
python -m ela_pipeline.training.train_generator \
  --train data/processed_template_id/train.jsonl \
  --dev data/processed_template_id/dev.jsonl \
  --output-dir results_llm_notes_template_id_e2 \
  --epochs 2 \
  --batch-size 8
```

Run executed with GPU access (outside sandbox; RTX 3090 available via `nvidia-smi`).

## Metrics

Source: `results_llm_notes_template_id_e2/evaluation_report.json`

- `eval_loss`: `0.6993013620376587`
- `eval_exact_match`: `0.0`
- `train_loss`: `2.4195492680256185`
- `train_runtime`: `12.2737`

## Comparison notes

- Current refreshed baseline (`results_llm_notes_refresh_data_processed_e2`) had lower eval loss (`0.415588...`).
- Template-ID dataset currently has very low target diversity (`10` unique targets after balance), which likely degrades note quality.

## Next required iteration

- Expand template mapping coverage/variants before final regression comparison (`accepted_note_rate`, `fallback_rate`, `rejected_nodes_total`).
