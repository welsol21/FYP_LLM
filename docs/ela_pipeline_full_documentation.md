# ELA Pipeline: Полная документация

## 1. Назначение
`ELA Pipeline` строит и валидирует иерархический JSON с лингвистическими элементами для английского текста.

Пайплайн реализует последовательность:
1. spaCy parsing
2. deterministic skeleton builder
3. TAM rules (tense/aspect/modality в поле `tense`)
4. optional local T5 generation (`linguistic_notes`)
5. strict validation (structure + frozen fields)

Авторитетный контракт структуры: `docs/sample.json`.

## 2. Контракт данных

### 2.1 Верхний уровень
JSON-объект вида:
- ключ: исходное предложение (`Sentence.content`)
- значение: узел `Sentence`

### 2.2 Типы узлов
Поддерживаются только:
- `Sentence`
- `Phrase`
- `Word`

### 2.3 Обязательные поля каждого узла
- `type`: `Sentence | Phrase | Word`
- `content`: string
- `tense`: string
- `linguistic_notes`: `string[]`
- `part_of_speech`: string
- `linguistic_elements`: array

### 2.4 Ограничения вложенности
- `Sentence.linguistic_elements` содержит только `Phrase`
- `Phrase.linguistic_elements` содержит только `Word`
- `Word.linguistic_elements` всегда пустой массив

### 2.5 Frozen-поля
После построения skeleton запрещено менять:
- `type`
- `content`
- `part_of_speech`
- структуру дочерних узлов

`linguistic_notes` и `tense` могут изменяться в процессе enrichment.

## 3. Структура проекта

### 3.1 Основной пакет
- `ela_pipeline/parse/spacy_parser.py` — загрузка spaCy pipeline
- `ela_pipeline/skeleton/builder.py` — построение contract-compliant skeleton
- `ela_pipeline/tam/rules.py` — rule-based TAM
- `ela_pipeline/validation/validator.py` — структурная и frozen валидация
- `ela_pipeline/validation/schema.py` — entrypoint структурной валидации
- `ela_pipeline/validation/logical.py` — entrypoint frozen-валидации
- `ela_pipeline/annotate/local_generator.py` — локальный T5 annotator
- `ela_pipeline/annotate/llm_annotator.py` — CLI-аннотация json-файла
- `ela_pipeline/inference/run.py` — production inference runner
- `ela_pipeline/dataset/build_dataset.py` — сбор train/dev/test jsonl
- `ela_pipeline/training/train_generator.py` — unified training entrypoint
- `ela_pipeline/corpus/normalize.py` — нормализация входного корпуса

### 3.2 Схемы и тесты
- `schemas/linguistic_contract.schema.json`
- `tests/test_validator.py`
- `tests/test_tam.py`
- `tests/test_pipeline.py`

## 4. Этапы пайплайна

### 4.1 Skeleton Builder
Вход: raw text.
Выход: JSON по контракту (`Sentence -> Phrase -> Word`).

Особенности:
- noun phrases из `sent.noun_chunks`
- verb phrase вокруг root-глагола
- prepositional phrases вокруг ADP
- fallback на один clause-подобный phrase, если кандидатов нет

### 4.2 TAM Rule Engine
Модуль `ela_pipeline/tam/rules.py`:
- определяет tense/aspect/voice/modality/polarity на последовательности токенов
- в output записывает нормализованное значение в `tense`

Практический результат:
- `should have + VBN` -> `past perfect`
- `will + verb` -> `future ...`

### 4.3 Local Notes Generation
Если задан `--model-dir`, запускается `LocalT5Annotator`:
- генерирует `linguistic_notes` для каждого узла
- сохраняет структуру/контент без изменений

Если `--model-dir` не задан:
- пайплайн возвращает валидный JSON
- `linguistic_notes` остаются пустыми массивами

### 4.4 Validation
Проверяется:
- структура и обязательные поля
- допустимые типы узлов
- согласованность ключа top-level и `Sentence.content`
- frozen-правила после enrichment

## 5. CLI

### 5.1 Сбор skeleton из JSONL
```bash
python -m ela_pipeline.build_skeleton --input input.jsonl --output skeleton.jsonl
```

`input.jsonl` должен содержать поле `text` в каждой строке.

### 5.2 Применение TAM
```bash
python -m ela_pipeline.run_tam --input skeleton.jsonl --output tam.jsonl
```

### 5.3 Полный inference
```bash
python -m ela_pipeline.inference.run \
  --text "The young scientist in the white coat carefully examined the strange artifact on the table." \
  --model-dir results_llm_notes_v3_t5-small_phrase/best_model
```

### 5.4 Аннотация существующего JSON
```bash
python -m ela_pipeline.annotate.llm_annotator \
  --input docs/sample.json \
  --output inference_results/sample_with_notes.json \
  --model-dir results_llm_notes_v3_t5-small_phrase/best_model
```

### 5.5 Сбор датасета
```bash
python -m ela_pipeline.dataset.build_dataset \
  --input linguistic_hierarchical_3000_v3.json \
  --output-dir data/processed
```

### 5.6 Обучение генератора
```bash
python -m ela_pipeline.training.train_generator \
  --train data/processed/train.jsonl \
  --dev data/processed/dev.jsonl \
  --output-dir artifacts/models/t5_notes
```

## 6. Формат входов/выходов

### 6.1 Вход в inference
- один аргумент `--text` (строка)

### 6.2 Выход inference
- JSON-файл в `inference_results/`
- имя `pipeline_result_<timestamp>.json`, если `--output` не указан

### 6.3 Ошибки
- несуществующий `model_dir` -> `FileNotFoundError` с понятным сообщением
- structural mismatch -> `ValueError` с перечислением ошибок валидации

## 7. Тестирование

Запуск:
```bash
python -m unittest discover -s tests -v
```

Покрытие проверяет:
- валидность `docs/sample.json`
- frozen-валидацию
- базовые кейсы TAM
- smoke-проход inference без генератора

## 8. Практические замечания

1. Рекомендуется запускать команды через активированное `.venv`.
2. Для генерации notes используйте реально существующую директорию модели.
3. `docs/sample.json` остается эталонным форматом для проверки совместимости.

## 9. Связанные документы
- `docs/TZ_ELA_Linguistic_Notes_Pipeline.docx`
- `docs/implementation_proposal.md`
- `docs/pipeline_cli.md`
- `docs/sample.json`
