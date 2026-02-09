# TODO

## Contract v2 Improvements

- [x] Enforce phrase length constraints:
  - [x] one-word phrases must be disallowed
  - [x] each `Phrase` node should contain at least 2 word tokens in `linguistic_elements`
  - [x] exclude simple determiner-led noun chunks (e.g., `the decision`)
- [x] Add stable graph identity fields:
  - [x] `node_id`
  - [x] `parent_id`
- [x] Add source alignment:
  - [x] `source_span.start`
  - [x] `source_span.end`
- [x] Add explicit syntactic role metadata:
  - [x] `grammatical_role` (`subject`, `predicate`, `object`, `modifier`, `adjunct`, etc.)
- [x] Split verbal grammar into separate fields instead of one overloaded `tense`:
  - [x] `tense`
  - [x] `aspect`
  - [x] `mood`
  - [x] `voice`
  - [x] `finiteness`
- [x] Add dependency linkage for word nodes:
  - [x] `dep_label`
  - [x] `head_id`
- [x] Add normalized morphology object:
  - [x] `features` (`number`, `person`, `case`, `degree`, `definiteness`, `verb_form`, etc.)
- [x] Replace plain `linguistic_notes: [string]` with typed note objects:
  - [x] `notes: [{text, kind, confidence, source}]`
  - [x] where `kind` in `semantic|syntactic|morphological|discourse`
  - [x] where `source` in `model|rule|fallback`
- [x] Add validation trace fields:
  - [x] `quality_flags`
  - [x] `rejected_candidates`
  - [x] `reason_codes`
- [x] Add versioning:
  - [x] `schema_version`

## Migration Plan

1. [x] Introduce new fields as optional in a backward-compatible `v2`.
2. [x] Update validators and pipeline to support dual mode (`v1` + `v2`).
3. [x] Promote core fields (`node_id`, `source_span`, `grammatical_role`) to required in strict `v2`.

## Next Quality Tasks

- [x] Deduplicate repeated entries in `rejected_candidates` and preserve attempt statistics (`count` + per-candidate reason trace in `rejected_candidate_stats`).
- [x] Remove `tense` from globally blocked note patterns in quality filter.
- [x] Adjust fallback template for `auxiliary verb` to avoid conflicts with note-quality validation.
- [x] Add regression test: fallback note for `auxiliary verb` must always be valid and non-empty.
