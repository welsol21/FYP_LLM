# ELA Pipeline: Full Documentation

## 1. Purpose
`ELA Pipeline` builds contract-compliant hierarchical linguistic JSON for English text.

End-to-end flow:
1. spaCy parsing
2. deterministic skeleton building
3. TAM enrichment (rule-based)
4. optional local T5 note generation
5. optional multilingual translation enrichment
6. validation (schema + frozen structure)

Authoritative compatibility contract: `docs/sample.json`.
Tool/model/data license registry: `docs/licenses_inventory.md`.

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
  - `dep_label` is the original dependency label from source parse (not phrase-internal relabeling)
- `features` (normalized morphology)
- `notes` typed objects: `{text, kind, confidence, source}`
- note trace fields: `quality_flags`, `rejected_candidates`, `rejected_candidate_stats`, `reason_codes`
- `schema_version`
- `translation` object:
  - sentence-level: `{source_lang, target_lang, model, text}`
  - node-level: `{source_lang, target_lang, text}`

### 2.5 Nesting Rules
- `Sentence` can contain only `Phrase`
- `Phrase` can contain only `Word`
- `Word` must have an empty `linguistic_elements`
- serialization order rule: `linguistic_elements` is emitted as the last field in each node object (`Sentence`, `Phrase`, `Word`) for stable readability.

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
  - `backoff_in_subtree` is a separate aggregate signal: `true` only when at least one descendant has local/subtree backoff.
- `matched_level_reason="tam_dropped"` is only valid for TAM-relevant nodes.
- Sentence-level backoff diagnostics:
  - `backoff_nodes_count`: count of all nodes with `backoff_used` in sentence tree (including the sentence node itself, if flagged).
  - `backoff_leaf_nodes_count`: count of non-sentence nodes with `backoff_used` (node-based, not deduplicated by span).
  - `backoff_aggregate_nodes_count`: count of aggregate backoff nodes (currently sentence-level own-node backoff only).
  - `backoff_unique_spans_count`: count of unique source spans among backoff leaf nodes.
  - Counter contract: `backoff_nodes_count = backoff_leaf_nodes_count + backoff_aggregate_nodes_count`.
  - Sentence aggregate rule: sentence is counted as aggregate backoff only when its own `template_selection.level != L1_EXACT`.
  - optional `backoff_summary` (debug mode): `nodes`, `leaf_nodes`, `aggregate_nodes_count`, `unique_spans`, `reasons`.

## 3. Validation Modes
`validate_contract` supports two modes:
- `v1`: backward-compatible baseline
- `v2_strict`: requires core v2 fields on each node (`node_id`, `source_span`, `grammatical_role`, `schema_version='v2'`)

Default mode is `v2_strict`.

Translation validation rules:
- if `translation` exists, it must be an object with non-empty `source_lang`, `target_lang`, and `text`.
- in `v2_strict`, `Sentence.translation.model` is required and must be non-empty.

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

### 4.5 Translation Enrichment (`ela_pipeline/translate/engine.py`)
- Optional runtime stage behind CLI flag `--translate`.
- Current provider: `m2m100` (`facebook/m2m100_418M`, MIT).
- Local deployment helper: `ela_pipeline/translate/prepare_m2m100.py` saves model to `artifacts/models/m2m100_418M`.
- Runtime model resolution policy:
  - if `--translation-model` is default (`facebook/m2m100_418M`) and local `artifacts/models/m2m100_418M` exists, local directory is used;
  - explicit custom `--translation-model` value always takes priority.
- Current output fields:
  - sentence-level `translation`: `{source_lang, target_lang, model, text}`
  - node-level `translation`: `{source_lang, target_lang, text}` (when node translation is enabled)
- Node translation strategy:
  - prefer `source_span` projection from sentence text over free node content translation,
  - reuse canonical translation via `ref_node_id`,
  - deduplicate calls for identical source spans/text within sentence.

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

### 5.6 Translation quality regression
```bash
.venv/bin/python -m ela_pipeline.inference.translation_quality_control \
  --source-lang en \
  --target-lang ru \
  --translation-provider m2m100 \
  --translate-nodes
```

One-time local model preparation:
```bash
.venv/bin/python -m ela_pipeline.translate.prepare_m2m100
```

## 6. Testing
Run in activated `.venv`:
```bash
.venv/bin/python -m unittest discover -s tests -v
```

Main tested areas:
- contract validity (`docs/sample.json`)
- strict mode behavior
- frozen structure checks
- phrase quality constraints
- notes quality and fallback logic
- inference pipeline smoke tests
- translation projection and translation-contract validation

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
