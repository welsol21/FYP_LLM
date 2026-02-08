# Предложение по полной реализации задачи ELA Linguistic Notes Pipeline

## 1. Фаза 1: Детерминированный core-пайплайн (spaCy + Skeleton + TAM + Validator)

- Создать модули в `src/ela_pipeline/`:
  - `corpus/normalize.py`
  - `parse/spacy_parser.py`
  - `skeleton/builder.py`
  - `tam/rules.py`
  - `validation/schema.py`
  - `validation/logical.py`
- Описать строгую JSON Schema: `schemas/linguistic_contract.schema.json`.
- Добавить CLI:
  - `python -m ela_pipeline.build_skeleton --input data/raw.jsonl --output data/skeleton.jsonl`
  - `python -m ela_pipeline.run_tam --input data/skeleton.jsonl --output data/tam.jsonl`
- Критерии:
  - одинаковый вход всегда дает одинаковую структуру и `content`;
  - тесты TAM проходят на эталонном наборе.

## 2. Фаза 2: Генерация датасета (LLM Annotator + строгая валидация)

- Добавить `src/ela_pipeline/annotate/llm_annotator.py` и шаблоны промптов.
- Ввести обязательную проверку “structure/content frozen” перед сохранением.
- Реализовать `dataset_builder.py`:
  - `input = skeleton + TAM + metadata`
  - `target = linguistic_notes` (рекомендуемый режим A).
- Разделить ошибки по категориям:
  - JSON parse error
  - schema error
  - content drift
  - logical contradiction
- Выход:
  - `data/processed/train.jsonl`, `dev.jsonl`, `test.jsonl`
  - `reports/annotation_quality.json`.

## 3. Фаза 3: Обучение локальной модели и оценка

- Рефакторинг текущих скриптов (`t5_training_script.py`, `train_llm_1_linguistic_notes_base_cpu.py`, `train_llm_1_linguistic_notes_base_cuda.py`) в единый тренер:
  - `src/ela_pipeline/training/train_generator.py`
  - конфиг `configs/train_t5_small.yaml`
- Поддержать CPU/CUDA через флаги/конфиг.
- Добавить оценку:
  - ROUGE-L, BLEU
  - доля структурно валидных outputs
  - выгрузка примеров для human review.
- Версионировать артефакты:
  - `artifacts/models/<run_id>/`
  - `artifacts/metrics/<run_id>.json`.

## 4. Фаза 4: Production inference runner

- Реализовать цепочку:
  - `parse -> skeleton -> TAM -> generator -> validator -> final JSON`
- Заменить текущий плоский формат инференса на иерархический JSON по контракту.
- Добавить entrypoint:
  - `python -m ela_pipeline.infer --text "..." --model artifacts/models/...`
- Ошибки:
  - только честный fail со структурированной диагностикой;
  - не возвращать “частично сломанный” JSON.

## Целевая структура репозитория

- `src/ela_pipeline/...`
- `schemas/...`
- `configs/...`
- `tests/unit/...`
- `tests/integration/...`
- `data/{raw,interim,processed}/...`
- `artifacts/{models,metrics,reports}/...`

## Приемочные критерии (по ТЗ)

- TAM accuracy >= 90% на 200 вручную проверенных предложениях.
- LLM annotation structural validation >= 99%.
- Inference JSON validity >= 99%.
- Human eval на 50+ предложений подтверждает полезность и согласованность нотаций.

## Текущий gap относительно ТЗ

- Уже есть базовые скрипты обучения/инференса генератора.
- Отсутствуют ключевые части deterministic pipeline:
  - Skeleton Builder
  - TAM Rule Engine
  - строгий Validator
  - оркестрация Dataset Builder
  - production-safe end-to-end inference.

## Рекомендуемый порядок реализации

1. Сначала полностью реализовать Фазу 1 (фундамент и защита от data drift).
2. Затем сделать минимальный vertical slice инференса (Фаза 4).
3. После этого довести Фазы 2 и 3 для масштабируемой подготовки датасета и качества модели.
