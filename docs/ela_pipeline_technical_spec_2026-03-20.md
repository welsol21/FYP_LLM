# Technical Specification: Next Stage of `ela_pipeline`

Date: 2026-03-20  
Status: Draft for implementation

## 1. Purpose

Continue development of `ela_pipeline` toward a classifier-first, contract-safe architecture in which:

- `spaCy + deterministic rules` remain the source of structural truth,
- `tabular ML` remains responsible for `cefr_level`,
- `T5` is used only for controlled lexical realization of pedagogical notes,
- `linguistic contract` is used as structural context, not as free-form generation output.

This specification covers the next implementation stage after the current `controlled` note mode.

## 2. Current State

The repository already contains the following working layers:

- skeleton construction:
  - `ela_pipeline/skeleton/builder.py`
- contract utilities:
  - `ela_pipeline/contract.py`
- structural validation:
  - `ela_pipeline/validation/validator.py`
- grammar-class to blueprint mapping:
  - `ela_pipeline/classifier/grammar_blueprints.py`
- deterministic template selection logic:
  - `ela_pipeline/annotate/template_registry.py`
- production inference path:
  - `ela_pipeline/inference/run.py`

The current field ownership decision is already fixed in:

- `docs/contract_field_ownership_2026-03-04.md`

The next gap is not basic parsing or CEFR prediction.  
The next gap is the explicit templating layer between:

1. validated `linguistic contract`
2. model input/output
3. controlled note realization

## 3. Target Outcome

After this stage, the note-generation flow must be:

1. raw text
2. `linguistic contract`
3. deterministic structural enrichment
4. CEFR prediction
5. blueprint generation
6. contract-to-template transformation
7. T5 lexical realization from template
8. validation that structure and classifier-owned fields are unchanged

In other words:

- the model must not receive raw unbounded input,
- the model must not invent structure,
- the model must only realize wording for a template derived from the contract.

## 4. Scope

### In Scope

- introduce explicit contract-to-template transformation for note generation
- define stable input template schema for T5
- define stable output schema for T5 note rendering
- integrate the template layer into `controlled` inference mode
- persist traceability fields in the contract
- add tests for template build, rendering, and validation

### Out of Scope

- redesign of skeleton builder
- replacing tabular CEFR classifier
- reintroducing DeBERTa into the production path
- free-form contract generation by T5
- redesign of translation / phonetic / synonym subsystems

## 5. Functional Requirements

### FR-1. Add explicit template builder

Implement a dedicated module that transforms a validated `linguistic contract` node into a model-facing template.

Recommended new module:

- `ela_pipeline/annotate/contract_template_builder.py`

Required input:

- validated node
- sentence text
- resolved `grammar_classes`
- resolved `cefr_level`
- `note_blueprints`
- optional rendering level: `elementary | intermediate | advanced`

Required output:

- deterministic template payload as `dict`
- stable `template_version`
- explicit `input_text` for the renderer
- explicit constraint payload for post-generation validation

### FR-2. Define template schema

The template payload must be explicit and versioned.

Minimum required fields:

- `template_version`
- `node_id`
- `node_type`
- `sentence_text`
- `node_text`
- `grammatical_role`
- `part_of_speech`
- `tam_features`
- `grammar_classes`
- `cefr_level`
- `target_note_level`
- `blueprint_text`
- `contract_context`
- `rendering_constraints`

`contract_context` must be derived from `linguistic contract` and may include:

- parent node text
- local subtree context
- dependency role
- phrase/sentence role

The template must be deterministic: identical contract input must produce identical template payload.

### FR-3. Add controlled renderer integration

Update the controlled note path so that T5 receives the templated input rather than raw contract fragments.

Primary integration point:

- `ela_pipeline/inference/run.py`

Renderer behavior:

- input: templated prompt derived from contract
- output: note wording only
- forbidden behavior: changing any structural or classifier-owned field

If rendering fails, the system must fall back to blueprint-based deterministic note text without corrupting the contract.

### FR-4. Persist traceability in contract

The contract must preserve enough metadata to explain how a note was produced.

Add or reuse trace fields such as:

- `note_template_version`
- `note_template_input`
- `note_render_source`
- `note_render_model`
- `note_render_status`

Allowed `note_render_source` values:

- `blueprint`
- `controlled_t5`
- `fallback`

These fields must be optional for backward compatibility but present in the new controlled path.

### FR-5. Preserve contract ownership boundaries

This implementation must respect the field ownership matrix.

T5 must never overwrite:

- `node_id`
- `parent_id`
- `source_span`
- `part_of_speech`
- `dep_label`
- `head_id`
- `features`
- `grammatical_role`
- `tam_construction`
- `grammar_classes`
- `cefr_level`
- `note_blueprints`

T5 may only produce:

- user-facing note wording

### FR-6. Add post-render validation

Add a validation step for templated rendering.

Minimum checks:

- generated note is non-empty when renderer reports success
- generated note remains single-note text, not JSON garbage
- contract-owned fields remain unchanged
- note text remains aligned with requested note level
- fallback path is recorded explicitly when used

Prefer extending existing validation/logical checks rather than creating a disconnected validator.

## 6. Non-Functional Requirements

- deterministic template build
- backward-compatible inference path
- no structural mutation by renderer
- test coverage for new template builder and integration path
- stable behavior under repeated identical inputs
- clear failure telemetry

## 7. Proposed Implementation Tasks

### Task 1. Template builder module

Create:

- `ela_pipeline/annotate/contract_template_builder.py`

Implement:

- template dataclass or typed dict
- contract node to template conversion
- prompt text assembly
- constraint extraction

### Task 2. Renderer interface update

Update:

- `ela_pipeline/annotate/controlled_renderer.py`

So that renderer accepts:

- normalized template payload or template-derived prompt text

instead of relying on loosely structured ad hoc input.

### Task 3. Inference pipeline integration

Update:

- `ela_pipeline/inference/run.py`

So that controlled note generation flow becomes:

- build contract
- enrich contract
- assign CEFR
- build note blueprints
- build rendering template
- render note
- validate output
- store trace fields

### Task 4. Validation updates

Update, where appropriate:

- `ela_pipeline/validation/validator.py`
- `ela_pipeline/validation/logical.py`

Add validation for:

- template trace fields
- controlled note output shape
- renderer non-mutation guarantees

### Task 5. Tests

Add tests for:

- deterministic template build
- template payload completeness
- renderer consuming template input
- fallback behavior
- invariant preservation for contract-owned fields
- integration of controlled mode in inference path

Recommended test files:

- `tests/test_contract_template_builder.py`
- `tests/test_controlled_renderer_template_mode.py`
- `tests/test_inference_template_pipeline.py`

## 8. Acceptance Criteria

This stage is accepted only if all conditions below are met.

### AC-1. Functional

- controlled note mode uses explicit contract-derived template input
- generated note text is produced from template rather than raw contract dump
- renderer never changes contract structure
- fallback path remains available and recorded

### AC-2. Validation

- contract passes existing schema/logic validation after rendering
- new traceability fields are present for new runs
- repeated identical input yields stable template payload

### AC-3. Testing

- all new tests pass
- relevant existing inference/validator tests still pass

## 9. Deliverables

- new template builder module
- updated controlled renderer integration
- updated inference path
- updated validation logic
- automated tests
- short implementation note in `docs/` describing template schema and runtime flow

## 10. Suggested Follow-Up Stage

After this stage is complete, the next technical stage should be:

1. node/subtree-level template specialization
2. richer constraint-aware lexical realization by CEFR band
3. validator that checks note wording against blueprint intent more strictly
4. optional offline dataset export:
   - `templated_input -> humanized_note`

That later stage must still preserve the same ownership rule:

- structure from contract
- CEFR from classifier
- wording from T5
