# TODO

## Contract v2 Improvements

- Enforce phrase length constraints:
  - one-word phrases must be disallowed
  - each `Phrase` node should contain at least 2 word tokens in `linguistic_elements`
- Add stable graph identity fields:
  - `node_id`
  - `parent_id`
- Add source alignment:
  - `source_span.start`
  - `source_span.end`
- Add explicit syntactic role metadata:
  - `grammatical_role` (`subject`, `predicate`, `object`, `modifier`, `adjunct`, etc.)
- Split verbal grammar into separate fields instead of one overloaded `tense`:
  - `tense`
  - `aspect`
  - `mood`
  - `voice`
  - `finiteness`
- Add dependency linkage for word nodes:
  - `dep_label`
  - `head_id`
- Add normalized morphology object:
  - `features` (`number`, `person`, `case`, `degree`, `definiteness`, `verb_form`, etc.)
- Replace plain `linguistic_notes: [string]` with typed note objects:
  - `notes: [{text, kind, confidence, source}]`
  - where `kind` in `semantic|syntactic|morphological|discourse`
  - where `source` in `model|rule|fallback`
- Add validation trace fields:
  - `quality_flags`
  - `rejected_candidates`
  - `reason_codes`
- Add versioning:
  - `schema_version`

## Migration Plan

1. Introduce new fields as optional in a backward-compatible `v2`.
2. Update validators and pipeline to support dual mode (`v1` + `v2`).
3. Promote core fields (`node_id`, `source_span`, `grammatical_role`) to required in strict `v2`.
