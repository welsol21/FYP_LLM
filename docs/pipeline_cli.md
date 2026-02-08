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
python -m ela_pipeline.inference.run --text "She should have trusted her instincts before making the decision." --model-dir artifacts/models/t5_notes/best_model
```

If `--model-dir` is omitted, the pipeline still returns contract-valid JSON with deterministic fields and TAM labels but empty `linguistic_notes`.
