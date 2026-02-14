# ELA Pipeline: Full Documentation

## 1. Purpose
`ELA Pipeline` builds contract-compliant hierarchical linguistic JSON for English text.

End-to-end flow:
1. spaCy parsing
2. deterministic skeleton building
3. TAM enrichment (rule-based)
4. optional local T5 note generation
5. validation (schema + frozen structure)

Authoritative compatibility contract: `docs/sample.json`.

## 2. Contract Model

### 2.1 Top-level
- JSON object keyed by sentence text.
- Each value is a `Sentence` node with `content` equal to the top-level key.

### 2.2 Node Types
Allowed types only:
- `Sentence`
- `Phrase`
- `Word`

### 2.3 Required Fields (all nodes)
- `type`
- `content`
- `tense`
- `linguistic_notes`
- `part_of_speech`
- `linguistic_elements`

### 2.4 Optional v2 Fields
- `aspect`, `mood`, `voice`, `finiteness`
- `node_id`, `parent_id`
- `source_span.start`, `source_span.end`
- `grammatical_role`
- `dep_label`, `head_id` (Word)
- `features` (normalized morphology)
- `notes` typed objects: `{text, kind, confidence, source}`
- note trace fields: `quality_flags`, `rejected_candidates`, `rejected_candidate_stats`, `reason_codes`
- `schema_version`

### 2.5 Nesting Rules
- `Sentence` can contain only `Phrase`
- `Phrase` can contain only `Word`
- `Word` must have an empty `linguistic_elements`

### 2.6 Phrase Quality Rules
- one-word phrases are disallowed
- simple determiner-led noun chunks are filtered out (for example, `the decision`)

### 2.7 Frozen Structure Rules
After skeleton creation, enrichment cannot change:
- `type`
- `content`
- `part_of_speech`
- stable graph and alignment fields when present
- children count/order and hierarchy

Only enrichment fields (notes/TAM-like metadata) may change.

### 2.8 Template Selection Trace Semantics
- `context_key_l1/l2/l3` are candidate context keys (what was attempted).
- `context_key_matched` is the effective key used for selection analytics.
- `tam_construction` remains the authoritative TAM channel even when `matched_key` is generic after `L2_DROP_TAM`.
- `quality_flags` contract:
  - `backoff_used` is required when `template_selection.level != L1_EXACT`.
  - `backoff_used` must not appear when `template_selection.level == L1_EXACT`.
- `matched_level_reason="tam_dropped"` is only valid for TAM-relevant nodes.
- Sentence-level backoff diagnostics:
  - `backoff_nodes_count`: count of nodes with `backoff_used` in sentence tree.
  - optional `backoff_summary` (debug mode): node ids + reasons.

## 3. Validation Modes
`validate_contract` supports two modes:
- `v1`: backward-compatible baseline
- `v2_strict`: requires core v2 fields on each node (`node_id`, `source_span`, `grammatical_role`, `schema_version='v2'`)

Default mode is `v2_strict`.

CLI exposure:
```bash
python -m ela_pipeline.inference.run --validation-mode v2_strict
python -m ela_pipeline.inference.run --validation-mode v1
```

## 4. Pipeline Stages

### 4.1 Skeleton Builder (`ela_pipeline/skeleton/builder.py`)
Creates deterministic `Sentence -> Phrase -> Word` structure with POS labels, dependency metadata, and morphology features.

### 4.2 TAM Rules (`ela_pipeline/tam/rules.py`)
Detects tense/aspect/voice/mood/finiteness at sentence and phrase levels.
Example: `should have + VBN` is interpreted as past-reference perfect at phrase/sentence level.

### 4.3 Notes Generation (`ela_pipeline/annotate/local_generator.py`)
If `--model-dir` is provided:
- generates model notes
- validates quality and suitability
- applies deterministic fallback if model output is weak
- stores both legacy `linguistic_notes` and typed `notes`
- records trace fields for rejected/accepted note decisions

If `--model-dir` is omitted:
- structure and TAM are still fully produced
- notes remain empty

### 4.4 Validation (`ela_pipeline/validation/validator.py`)
- structural validity
- field type/range checks
- mode-aware strictness
- frozen structure integrity after enrichment

## 5. CLI Usage

### 5.1 Build dataset
```bash
python -m ela_pipeline.dataset.build_dataset --input linguistic_hierarchical_3000_v3.json --output-dir data/processed
```

### 5.2 Train local generator
```bash
python -m ela_pipeline.training.train_generator --train data/processed/train.jsonl --dev data/processed/dev.jsonl --output-dir artifacts/models/t5_notes
```

### 5.3 Run full inference
```bash
python -m ela_pipeline.inference.run --text "She should have trusted her instincts before making the decision." --model-dir results_llm_notes_v3_t5-small_phrase/best_model
```

### 5.4 Run strict v2 inference
```bash
python -m ela_pipeline.inference.run --text "She should have trusted her instincts before making the decision." --model-dir results_llm_notes_v3_t5-small_phrase/best_model --validation-mode v2_strict
```

Note: the same command without `--validation-mode` runs in `v2_strict` by default.

### 5.5 Annotate existing JSON
```bash
python -m ela_pipeline.annotate.llm_annotator --input docs/sample.json --output inference_results/sample_with_notes.json --model-dir results_llm_notes_v3_t5-small_phrase/best_model
```

## 6. Testing
Run in activated `.venv`:
```bash
python -m unittest discover -s tests -v
```

Main tested areas:
- contract validity (`docs/sample.json`)
- strict mode behavior
- frozen structure checks
- phrase quality constraints
- notes quality and fallback logic
- inference pipeline smoke tests

## 7. Practical Notes
1. Use `.venv` to avoid dependency mismatch.
2. If `--model-dir` path does not exist, inference raises a clear `FileNotFoundError`.
3. Use `docs/sample.json` as the canonical compatibility target.

## 8. Related Documents
- `docs/pipeline_cli.md`
- `docs/TODO.md`
- `docs/implementation_proposal.md`
- `docs/sample.json`
- `docs/TZ_ELA_Linguistic_Notes_Pipeline.docx`
