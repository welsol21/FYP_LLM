# Contract Field Ownership Matrix

Date: 2026-03-04  
Status: Active architecture decision

## Purpose

This document fixes the ownership boundary for contract fields.

The project must not drift into a "single model predicts the whole contract" design.

Instead:

1. `spaCy + deterministic rules` own structural truth.
2. `tabular ML` owns CEFR prediction.
3. `T5` owns only user-facing note wording.

`DeBERTa` remains an experimental branch, not a production blocker.

## Field Ownership

| Contract field / field family | Primary source of truth | Why |
| --- | --- | --- |
| `content` | parser / source text alignment | direct text span |
| `type` (`Sentence` / `Phrase` / `Word`) | parser / builder rules | deterministic tree construction |
| `linguistic_elements` | parser / builder rules | deterministic graph structure |
| `node_id`, `parent_id` | builder | deterministic graph identity |
| `source_span` | parser alignment / builder | deterministic alignment |
| `part_of_speech` | spaCy | parser-native structural field |
| `dep_label`, `head_id` | spaCy + builder mapping | parser-native dependency field |
| `features` (morphology) | spaCy normalization | parser-native morphology field |
| `grammatical_role` | rules over dependency structure | deterministic interpretation layer |
| `tense`, `aspect`, `mood`, `voice`, `finiteness` | rules over morph + dependency + auxiliaries | deterministic grammar extraction |
| `tam_construction` | rules over morph + dependency + auxiliaries | normalized structural interpretation |
| `grammar_classes` | rules-first mapper over parse/TAM signals | pedagogical labels derived from structural evidence |
| `cefr_level` | tabular ML baseline over structural evidence | prediction task; not directly derivable from parse |
| `note_blueprints` | rules/templates keyed by `grammar_classes` + `cefr_level` | controlled pedagogical scaffold |
| `generated_notes` / `linguistic_notes` | T5 controlled rendering from blueprints | user-facing wording only |
| `translations` | translation provider layer | not a classification task |
| `phonetic` | phonetic provider layer | not a classification task |
| `synonyms` | synonym provider layer | not a classification task |
| telemetry / quality trace fields | validators / runtime | system trace, not ML truth |

## Practical Rules

### 1. What must stay rule-based

The following must not depend on a classifier as the primary source:

- syntax tree shape
- POS / dependency / morphology
- TAM-style structural grammar fields
- graph identity / spans / node relations

### 2. What is allowed to be predicted

Currently the only required prediction layer is:

- `cefr_level`

Optional prediction layer:

- `grammar_classes`, but only as a secondary validator/fallback if rule coverage proves insufficient

Current preferred design:

- `grammar_classes` = rules-first
- `cefr_level` = tabular ML

### 3. What generation is allowed to do

`T5` is not allowed to invent structural truth.

`T5` may only:

- rewrite blueprint content into human-readable pedagogical note text

`T5` must never overwrite:

- `cefr_level`
- `grammar_classes`
- TAM / dependency / morphology truth fields

## Current State (2026-03-04)

- `CEFR` on the merged full-ladder dataset is already near-perfect with the tabular baseline.
- The production tabular CEFR path uses the `runtime_stable` feature profile.
- `dataset_source` and `treebank` are intentionally excluded from that production profile because ablation showed no CEFR quality loss after removing them.
- `grammar_label` is also learnable with tabular ML and clearly not blocked by corpus coverage.
- Current `DeBERTa` training remains worse than the tabular baselines.

Therefore:

- `DeBERTa` is removed from the critical production path for now.
- The active backend target is:
  - `spaCy/rules -> structural truth + grammar classes`
  - `tabular ML -> CEFR`
  - `T5 -> notes from blueprints`
