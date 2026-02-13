# ELA Pipeline CLI

## 1) Fetch raw source files

```bash
python -m ela_pipeline.dataset.fetch_raw_sources \
  --output-dir data/raw_sources \
  --ud-limit 1200 --tatoeba-limit 1200 --wikinews-limit 600
```

## 2) Build licensed ingestion corpus

```bash
python -m ela_pipeline.dataset.build_ingestion_corpus \
  --config data/source_configs/ingestion_sources_bootstrap.json \
  --output-jsonl data/raw_sources/ingested_sentences.jsonl \
  --report-json docs/ingestion_report_2026-02-13.json
```

## 3) Extract sentence/phrase/word nodes (3k/9k/18k)

```bash
python -m ela_pipeline.dataset.extract_ingested_nodes \
  --input-jsonl data/raw_sources/ingested_sentences.jsonl \
  --output-dir data/processed_ingested_nodes \
  --sentence-quota 3000 --phrase-quota 9000 --word-quota 18000
```

## 4) Ingestion QA report

```bash
python -m ela_pipeline.dataset.report_ingestion_quality \
  --ingested-jsonl data/raw_sources/ingested_sentences.jsonl \
  --nodes-dir data/processed_ingested_nodes \
  --output-json docs/ingestion_quality_report_2026-02-13.json
```

## 5) Build training dataset from ingested nodes

```bash
python -m ela_pipeline.dataset.build_dataset_from_ingested \
  --nodes-dir data/processed_ingested_nodes \
  --output-dir data/processed_from_ingested_template_id \
  --min-unique-targets 12 --max-top1-share 0.45 --min-active-template-ids 12
```

## 6) Build dataset splits (legacy hierarchical input)

```bash
python -m ela_pipeline.dataset.build_dataset --input <hierarchical_input.json> --output-dir data/processed
```

## 7) Train local generator

```bash
python -m ela_pipeline.training.train_generator --train data/processed/train.jsonl --dev data/processed/dev.jsonl --output-dir artifacts/models/t5_notes --seed 42 --learning-rate 5e-5
```

Training writes reproducibility artifacts:
- `artifacts/models/t5_notes/training_config.json`
- `artifacts/models/t5_notes/evaluation_report.json`

Optional hard-negative loop from rejected candidates:

```bash
python -m ela_pipeline.validation.build_hard_negatives --input inference_results/pipeline_result_latest.json --output artifacts/quality/hard_negative_patterns.json --min-count 2 --max-items 200
```

To apply these patterns during note validation, set:

```bash
export ELA_HARD_NEGATIVE_PATTERNS=artifacts/quality/hard_negative_patterns.json
```

## 8) Run production inference

```bash
python -m ela_pipeline.inference.run --text "She should have trusted her instincts before making the decision." --model-dir results_llm_notes_v3_t5-small_phrase/best_model --note-mode template_only
```

`v2_strict` is now the default mode.
Legacy compatibility mode (`v1`) is still available only when explicitly requested:

```bash
python -m ela_pipeline.inference.run --text "She should have trusted her instincts before making the decision." --model-dir results_llm_notes_v3_t5-small_phrase/best_model --validation-mode v1
```

If `--model-dir` is omitted, the pipeline still returns contract-valid JSON with deterministic fields and TAM labels but empty `linguistic_notes`.
In `v2_strict`, each node must include `node_id`, `source_span`, `grammatical_role`, and `schema_version`, and uses real JSON `null` (not string `"null"`) in nullable TAM fields.

Note: the path `artifacts/models/t5_notes/best_model` is valid only if you trained a model into `artifacts/models/t5_notes` in this workspace. If that directory does not exist, pass an existing local model directory (for example `results_llm_notes_v3_t5-small_phrase/best_model`).
