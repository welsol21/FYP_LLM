# ELA Pipeline: Full Documentation

## 1. Purpose
`ELA Pipeline` builds and validates hierarchical linguistic JSON for English text.

Pipeline flow:
1. spaCy parsing
2. deterministic skeleton builder
3. TAM rules (tense/aspect/modality reflected in `tense`)
4. optional local T5 generation (`linguistic_notes`)
5. strict validation (structure + frozen fields)

Authoritative structure contract: `docs/sample.json`.

## 2. Data Contract

### 2.1 Top-level
JSON object where:
- key: original sentence (`Sentence.content`)
- value: `Sentence` node

### 2.2 Node Types
Supported node types only:
- `Sentence`
- `Phrase`
- `Word`

### 2.3 Required Fields on Every Node
- `type`: `Sentence | Phrase | Word`
- `content`: string
- `tense`: string
- `linguistic_notes`: `string[]`
- `part_of_speech`: string
- `linguistic_elements`: array

### 2.4 Nesting Rules
- `Sentence.linguistic_elements` can contain only `Phrase`
- `Phrase.linguistic_elements` can contain only `Word`
- `Word.linguistic_elements` must be an empty array

### 2.5 Frozen Fields
After skeleton generation, the following cannot be changed:
- `type`
- `content`
- `part_of_speech`
- child structure

`linguistic_notes` and `tense` may be updated during enrichment.

## 3. Project Structure

### 3.1 Core Package
- `ela_pipeline/parse/spacy_parser.py` - spaCy pipeline loading
- `ela_pipeline/skeleton/builder.py` - contract-compliant skeleton construction
- `ela_pipeline/tam/rules.py` - rule-based TAM
- `ela_pipeline/validation/validator.py` - structural and frozen validation
- `ela_pipeline/validation/schema.py` - structural validation entrypoint
- `ela_pipeline/validation/logical.py` - frozen validation entrypoint
- `ela_pipeline/annotate/local_generator.py` - local T5 annotator
- `ela_pipeline/annotate/llm_annotator.py` - CLI annotator for existing JSON
- `ela_pipeline/inference/run.py` - production inference runner
- `ela_pipeline/dataset/build_dataset.py` - train/dev/test JSONL builder
- `ela_pipeline/training/train_generator.py` - unified training entrypoint
- `ela_pipeline/corpus/normalize.py` - corpus normalization

### 3.2 Schemas and Tests
- `schemas/linguistic_contract.schema.json`
- `tests/test_validator.py`
- `tests/test_tam.py`
- `tests/test_pipeline.py`

## 4. Pipeline Stages

### 4.1 Skeleton Builder
Input: raw text.
Output: contract JSON (`Sentence -> Phrase -> Word`).

Behavior:
- noun phrases from `sent.noun_chunks`
- verb phrase around sentence root verb
- prepositional phrases around ADP tokens
- fallback to one clause-like phrase if no candidates are found

### 4.2 TAM Rule Engine
Module: `ela_pipeline/tam/rules.py`
- detects tense/aspect/voice/modality/polarity over token sequences
- writes normalized result to `tense`

Practical outcomes:
- `should have + VBN` -> `past perfect`
- `will + verb` -> `future ...`

### 4.3 Local Notes Generation
If `--model-dir` is set, `LocalT5Annotator` runs:
- generates `linguistic_notes` for each node
- preserves structure and frozen fields

If `--model-dir` is not set:
- pipeline still returns valid contract JSON
- `linguistic_notes` remain empty arrays

### 4.4 Validation
Checks include:
- required structure and fields
- allowed node types
- consistency between top-level key and `Sentence.content`
- frozen rules after enrichment

## 5. CLI

### 5.1 Build Skeleton from JSONL
```bash
python -m ela_pipeline.build_skeleton --input input.jsonl --output skeleton.jsonl
```

`input.jsonl` must include a `text` field in each row.

### 5.2 Apply TAM
```bash
python -m ela_pipeline.run_tam --input skeleton.jsonl --output tam.jsonl
```

### 5.3 Full Inference
```bash
python -m ela_pipeline.inference.run \
  --text "The young scientist in the white coat carefully examined the strange artifact on the table." \
  --model-dir results_llm_notes_v3_t5-small_phrase/best_model
```

### 5.4 Annotate Existing JSON
```bash
python -m ela_pipeline.annotate.llm_annotator \
  --input docs/sample.json \
  --output inference_results/sample_with_notes.json \
  --model-dir results_llm_notes_v3_t5-small_phrase/best_model
```

### 5.5 Build Dataset
```bash
python -m ela_pipeline.dataset.build_dataset \
  --input linguistic_hierarchical_3000_v3.json \
  --output-dir data/processed
```

### 5.6 Train Generator
```bash
python -m ela_pipeline.training.train_generator \
  --train data/processed/train.jsonl \
  --dev data/processed/dev.jsonl \
  --output-dir artifacts/models/t5_notes
```

## 6. Input/Output Formats

### 6.1 Inference Input
- single `--text` argument

### 6.2 Inference Output
- JSON file in `inference_results/`
- default name: `pipeline_result_<timestamp>.json` when `--output` is not provided

### 6.3 Errors
- missing `model_dir` -> `FileNotFoundError` with a clear message
- structural mismatch -> `ValueError` with detailed validation errors

## 7. Testing

Run:
```bash
python -m unittest discover -s tests -v
```

Coverage validates:
- `docs/sample.json` contract validity
- frozen validation behavior
- baseline TAM cases
- inference smoke pass without generator

## 8. Practical Notes

1. Run commands inside activated `.venv`.
2. For notes generation, provide an existing local model directory.
3. `docs/sample.json` remains the authoritative compatibility reference.

## 9. Related Documents
- `docs/TZ_ELA_Linguistic_Notes_Pipeline.docx`
- `docs/implementation_proposal.md`
- `docs/pipeline_cli.md`
- `docs/sample.json`
