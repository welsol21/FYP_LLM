# ELA Pipeline CLI

## 1) Build dataset splits

```bash
python -m ela_pipeline.dataset.build_dataset --input linguistic_hierarchical_3000_v3.json --output-dir data/processed
```

## 2) Train local generator

```bash
python -m ela_pipeline.training.train_generator --train data/processed/train.jsonl --dev data/processed/dev.jsonl --output-dir artifacts/models/t5_notes
```

## 3) Run production inference

```bash
python -m ela_pipeline.inference.run --text "She should have trusted her instincts before making the decision." --model-dir results_llm_notes_v3_t5-small_phrase/best_model --validation-mode v2_strict
```

Legacy compatibility mode (`v1`) if needed:

```bash
python -m ela_pipeline.inference.run --text "She should have trusted her instincts before making the decision." --model-dir results_llm_notes_v3_t5-small_phrase/best_model --validation-mode v1
```

If `--model-dir` is omitted, the pipeline still returns contract-valid JSON with deterministic fields and TAM labels but empty `linguistic_notes`.
In `v2_strict`, each node must include `node_id`, `source_span`, `grammatical_role`, and `schema_version`, and uses real JSON `null` (not string `"null"`) in nullable TAM fields.

Note: the path `artifacts/models/t5_notes/best_model` is valid only if you trained a model into `artifacts/models/t5_notes` in this workspace. If that directory does not exist, pass an existing local model directory (for example `results_llm_notes_v3_t5-small_phrase/best_model`).
