# FYP_LLM: ELA Linguistic Notes Pipeline

Репозиторий содержит end-to-end пайплайн для построения лингвистического JSON по английскому тексту:
- deterministic parsing/structure (spaCy + правила)
- rule-based TAM
- optional local T5 generation для `linguistic_notes`
- строгая валидация по контракту

Контракт-эталон: `docs/sample.json`.

## Что реализовано

1. Core pipeline (`ela_pipeline`)
- `build_skeleton`
- `run_tam`
- `inference.run`
- validators (schema + frozen)

2. Data and training
- dataset builder: `ela_pipeline.dataset.build_dataset`
- unified trainer: `ela_pipeline.training.train_generator`

3. Документация и тесты
- полный гайд: `docs/ela_pipeline_full_documentation.md`
- CLI quick guide: `docs/pipeline_cli.md`
- тесты: `tests/`

## Быстрый старт

### 1) Установка зависимостей
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2) Проверка тестов
```bash
python -m unittest discover -s tests -v
```

### 3) Inference без генератора
```bash
python -m ela_pipeline.inference.run --text "She should have trusted her instincts before making the decision."
```

### 4) Inference с локальной моделью
```bash
python -m ela_pipeline.inference.run \
  --text "The young scientist in the white coat carefully examined the strange artifact on the table." \
  --model-dir results_llm_notes_v3_t5-small_phrase/best_model
```

## Основные команды

### Build dataset splits
```bash
python -m ela_pipeline.dataset.build_dataset \
  --input linguistic_hierarchical_3000_v3.json \
  --output-dir data/processed
```

### Train local generator
```bash
python -m ela_pipeline.training.train_generator \
  --train data/processed/train.jsonl \
  --dev data/processed/dev.jsonl \
  --output-dir artifacts/models/t5_notes
```

### Build skeleton and TAM via JSONL
```bash
python -m ela_pipeline.build_skeleton --input input.jsonl --output skeleton.jsonl
python -m ela_pipeline.run_tam --input skeleton.jsonl --output tam.jsonl
```

## Структура проекта

- `ela_pipeline/` — код пайплайна
- `schemas/` — JSON schema
- `data/processed/` — train/dev/test jsonl
- `inference_results/` — результаты инференса
- `docs/` — документация
- `tests/` — unit/smoke тесты

## Документация

- Полная: `docs/ela_pipeline_full_documentation.md`
- Краткая по командам: `docs/pipeline_cli.md`
- План реализации: `docs/implementation_proposal.md`
- ТЗ: `docs/TZ_ELA_Linguistic_Notes_Pipeline.docx`
