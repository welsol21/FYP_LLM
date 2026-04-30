# ELA Structural Runtime TODO

Date: 2026-04-27  
Branch: `feature-ela-structural-runtime`  
Status: active working note for resume after pauses

## Progress Log

### 2026-04-27

- Fast-track scope locked to `sentence-only`, target `5k-8k` rows.
- Phrase and word layers explicitly deferred to feedback-driven expansion.
- Added extractor:
  - `scripts/build_sentence_note_seed_from_v35_csv.py`
- Extracted a clean seed pack from `/home/vlad/Downloads/v35_fixed_clean.csv`:
  - output: `data/processed_sentence_seed/v35_sentence_seed_v1.jsonl`
  - report: `data/processed_sentence_seed/v35_sentence_seed_v1.report.json`
- Current measured yield from that CSV:
  - `77` kept sentence rows
  - `42` unique note texts
- Current interpretation:
  - the CSV is not a usable main dataset
  - it is usable as a small sentence-level seed donor
  - it should supplement, not replace, the main curated sentence note pool
- Added fast-track pool builder:
  - `scripts/build_fasttrack_sentence_note_pool.py`
- Built canonical cycle-1 sentence note pool:
  - output: `data/processed_sentence_seed/fasttrack_sentence_note_pool_v1.jsonl`
  - report: `data/processed_sentence_seed/fasttrack_sentence_note_pool_v1.report.json`
- Current measured pool size:
  - `244` sentence rows
  - `209` unique note texts
  - `229` unique sentence texts
- Current interpretation:
  - cycle-1 note pool is already near the lower target bound for transferable sentence units
  - if projection yield is healthy, this may already be enough to reach the `5k` lower dataset target
  - next bottleneck is no longer source assembly but projection yield and export quality
- Locked raw projection base for cycle 1:
  - `data/raw_sources/ingested_sentences.jsonl`
  - current raw source rows: `2973`
  - current projected sentence nodes after parse split: `3239`
- Added projection-safe pool builder:
  - `scripts/build_projection_safe_sentence_note_pool.py`
- Built projection-safe sentence note pool:
  - `135` rows
  - `118` unique note texts
- First sentence-only projection results from projection-safe pool:
  - covered sentence nodes: `784`
  - sentence note candidates total with cap=3: `1835`
  - sentence note candidates total with cap=8: `3207`
- Important finding:
  - raising `max_sentence_candidates` increases candidate count but does not increase covered sentence nodes
  - therefore the current bottleneck is coverage, not candidate cap
- Patched exporter fallback in:
  - `ela_pipeline/dataset/build_t5_dataset_from_projected_corpus.py`
  - new behavior: fallback to candidate note text when canonical template is incompatible or missing
- Export result after fallback patch on topic-safe projection:
  - `350` rows
  - `19` unique targets
  - `0` empty targets
- Added sentence family indexing to:
  - `ela_pipeline/dataset/project_template_notes_onto_corpus.py`
- Added family-aligned sentence pool builder:
  - `scripts/build_family_aligned_sentence_note_pool.py`
- Built family-aligned sentence note pool:
  - `167` rows
  - `167` unique note texts
- Family-aligned projection results:
  - covered sentence nodes: `784`
  - total sentence candidates: `3497`
- Export result after family-aligned projection:
  - `400` rows
  - `29` unique targets
  - `0` empty targets
- Critical feasibility finding:
  - with the current raw corpus we only have `3239` parsed sentence nodes
  - the current exporter selects `one` target per sentence node
  - therefore a `5k-8k` sentence-only dataset is impossible in the current regime
  - to exceed that ceiling we must either:
    - expand the raw corpus substantially, or
    - allow multiple training rows per covered sentence node, or
    - change the target scope again
- Added multi-target sentence export support in:
  - `ela_pipeline/dataset/build_t5_dataset_from_projected_corpus.py`
  - new CLI option: `--max-sentence-targets-per-node`
- Verified path 2 on real projected data:
  - family-aligned single-target export: `400` rows, `29` unique targets
  - family-aligned multi-target export with `max_sentence_targets_per_node=4`: `1121` rows, `51` unique targets
- Current interpretation:
  - path 2 is valid and materially increases usable dataset size
  - it still does not reach `5k-8k` on the current raw corpus
  - but it removes the previous hard ceiling of roughly `one row per covered sentence node`
  - the next gains must come from one or more of:
    - larger raw corpus
    - higher per-node target cap
    - stronger sentence-family coverage
    - looser but still safe target-cap strategy

## Goal

Bring production note generation and its training data in line with the ELA idea:

1. sentence -> phrase -> word recursive structure remains the source of truth
2. nodes carry abstract grammatical attributes
3. models learn from structural patterns first
4. lexical realization is a separate controlled layer

Target claim we want to make true in code:

> The system generalises across unseen vocabulary that shares the same grammatical shape.

## Current Reality

### Already true

- Runtime contract is recursive `Sentence -> Phrase -> Word`.
- Structural truth is owned by parser/rules, not by T5.
- Nodes carry abstract fields such as `type`, `part_of_speech`, `grammatical_role`, `tense/aspect/mood/voice/finiteness`, `cefr_level`.
- `grammar_classes` and `note_blueprints` are built outside free-form generation.
- `controlled` mode uses T5 for wording, not for full-contract generation.

### Not yet true enough

- Production controlled mode does not yet use explicit contract-template payloads from `ela_pipeline/annotate/contract_template_builder.py`.
- T5 rewrite currently mutates `note_blueprints`, which breaks the ownership boundary.
- Runtime does not validate T5 output with note-quality gates before accepting it.
- Prompts still use too much surface lexical context for the claim "shape-first generalisation" to be fully defensible.
- Training data still contains substantial lexical/book-specific supervision rather than a clean structural-to-note realization task.

## Verified Gaps

### Gap 1. Blueprint ownership is violated

File: `ela_pipeline/inference/run.py`

- `_rewrite_controlled_notes_with_t5()` writes rendered text back into `note_blueprints`.
- Then `_apply_controlled_notes()` copies those mutated blueprint values into `linguistic_notes`.

What must change:

- `note_blueprints` must remain classifier/rule-owned scaffold.
- T5 output must go only into user-facing note fields.

### Gap 2. Explicit template builder exists but is not in the critical path

Files:

- `ela_pipeline/annotate/contract_template_builder.py`
- `ela_pipeline/inference/run.py`

What must change:

- `run_pipeline()` should build a versioned rendering payload before T5.
- renderer should accept structured template input, not only ad hoc prompt pieces.

### Gap 3. No proper runtime note-quality gate

Files:

- `ela_pipeline/validation/notes_quality.py`
- `ela_pipeline/inference/run.py`

What must change:

- after T5 render, run `sanitize_note()` and `is_valid_note()`
- on failure, fall back to blueprint wording
- log render status and fallback reason

### Gap 4. Dataset templating is still too lexical and sometimes corrupts grammar labels

File: `ela_pipeline/dataset/template_slot_book_notes.py`

Known issue:

- broad substitutions such as `"noun"` -> `{{HEAD_NOUN}}` can corrupt multiword conceptual notes like `"noun phrase"`

What must change:

- slot parametrization must prefer safe grammatical phrases
- avoid replacing broad grammar terms when they are part of a larger label
- keep structural abstraction but do not destroy pedagogical meaning

## Work Order

### Phase 1. Runtime correctness

1. stop mutating `note_blueprints`
2. add separate rendered-note path
3. add trace fields for render source/model/status
4. add post-render validation and fallback
5. add tests for ownership invariants

Definition of done:

- T5 never changes `grammar_classes`, `cefr_level`, TAM fields, POS, spans, or blueprint text
- invalid T5 note falls back safely

### Phase 2. Template-first controlled rendering

1. integrate `contract_template_builder` into `run_pipeline()`
2. update `ControlledT5NoteRenderer` to consume template payloads
3. persist `note_template_version` and `note_template_input`
4. add deterministic template tests

Definition of done:

- production controlled mode has an explicit versioned template layer
- identical contract input yields identical render payload

### Phase 3. Shape-first dataset refactor

1. define a training target where model input is structural payload, not raw book note
2. reduce lexical leakage from source-side inputs
3. separate blueprint generation from lexical realization supervision
4. add evaluation for same-shape/different-lexicon robustness

Definition of done:

- dataset supports the claim that T5 is learning note realization from grammatical shape

## Dataset Strategy For ELA Idea

We need to split the pipeline into two distinct learning problems.

### Problem A. Structural interpretation

Purpose:

- map parse-derived evidence to `grammar_classes`
- map node evidence to `cefr_level`

How it should be trained:

- input features should be structural, not lexical-first
- keep using parser/rule/TAM features as primary evidence
- lexical identity can be present only as weak supporting context, not as the core signal

This is already mostly aligned with the architecture.

### Problem B. Note realization

Purpose:

- turn controlled structural payload into short pedagogical note wording

This is the dataset that needs the biggest cleanup.

The model should learn:

- given node type, grammatical role, TAM profile, grammar class, note level, and bounded local context
- produce one short note that explains the grammatical function

The model should not learn:

- to recover the note from memorized book wording
- to depend on specific content words when the grammar shape alone is enough
- to invent structure that is not already in the contract

## Proposed Training Row Schema For Note Realization

Each row should contain:

- `input_mode`
- `template_version`
- `node_type`
- `part_of_speech`
- `grammatical_role`
- `tam_features`
- `grammar_classes`
- `cefr_level`
- `target_note_level`
- `contract_context`
- `rendering_constraints`
- `input_text`
- `target_note`
- `source_type`
- `quality_flags`

### Input discipline

Preferred input ordering:

1. structural identity
2. grammar class labels
3. CEFR target
4. constrained local context
5. optional bounded node text only where needed

Raw sentence text should be included only when it materially disambiguates the grammar pattern.

### Output discipline

Target should be:

- one short pedagogical note
- no JSON
- no field names
- no template instructions
- no book-internal references
- no lexical overfitting cues unless grammatically required

## Dataset Sources We Should Keep

- contract-derived blueprints from runtime-compatible nodes
- curated book-note rows that can be normalized into structural templates
- synthetic paraphrases of blueprint notes when they preserve the same structural meaning
- QC-approved rows only

## Dataset Sources We Should Downgrade Or Exclude

- rows whose supervision depends mainly on quoted lexical items
- notes tied to book formatting, chapter references, or editorial markup
- rows where target wording cannot be justified from structural evidence
- rows where note meaning changes if vocabulary changes but grammar shape stays the same

## Dataset Build Plan

### Dataset v1: strict realization dataset

Build only from rows where:

- template slots are fully resolved or intentionally abstract
- target note can be explained from `grammar_classes + role + TAM + level`
- no book meta references remain
- no unresolved lexical leakage flags remain

Use this dataset to train the first template-first renderer.

### Dataset v2: controlled lexical context dataset

Add rows where small lexical cues are allowed because the grammar pattern needs them.

Examples:

- relative marker choice
- stranded vs fronted preposition
- tag-question auxiliary/pronoun
- lexicalized multiword constructions where the grammar class depends on the expression

This should be a second-stage expansion, not the base dataset.

## Automatic Dataset Build Plan For 10k-25k+

This is the main operational plan for solving the current blocker:

- automatically produce `10k-25k+` usable training rows
- without manual annotation at that scale
- by projecting a smaller pool of transferable note units onto a larger natural corpus

### Core principle

Do not try to extract `10k-25k` gold note rows directly from books.

Instead:

1. extract `~700-1500` transferable note units
2. normalize them into template-aware note packs
3. project them onto a large parsed natural corpus
4. merge all projections
5. normalize and QC candidates
6. export final train/dev/test rows

### Target scale model

Expected multiplier:

- `1` transferable note unit -> `~15-40` matched corpus nodes

Therefore:

- `700` note units can yield `~10k-20k` raw candidates
- `1000` note units can yield `~20k-30k` raw candidates
- `1500` note units can yield `~35k-60k` raw candidates

After QC, dedup, and capping:

- expect roughly `40%-60%` retention

This makes `10k-25k+` realistic if the note-pack coverage is broad enough.

## Automatic Build TODO

### A. Inventory the existing automatic sources

Goal:

- make a complete source map of all current extractors and book-note builders
- identify which ones yield sentence, phrase, and word note units

Concrete files to inventory:

- `scripts/extract_leech_glossary_pairs.py`
- `scripts/extract_cambridge_learner_pairs.py`
- `scripts/extract_cambridge_grammar_phrase_pairs.py`
- `ela_pipeline/dataset/extract_wiktionary_grammar_pairs.py`
- `ela_pipeline/dataset/extract_farlex_grammar_pairs.py`
- `ela_pipeline/dataset/extract_egiu_grammar_pairs.py`
- `ela_pipeline/dataset/extract_cobuild_advanced_dict_pairs.py`
- `ela_pipeline/dataset/extract_english_for_everyone_practice_ocr_pairs.py`
- `ela_pipeline/dataset/build_rulebook_note_context_pairs.py`
- `ela_pipeline/dataset/build_oxford_targeted_note_context_pairs.py`
- `ela_pipeline/dataset/build_cobuild_2011_book_note_rows_v1.py`
- `ela_pipeline/dataset/build_mark_lester_book_note_rows_v1.py`
- `ela_pipeline/dataset/build_azar_basic_book_note_rows_v1.py`
- `ela_pipeline/dataset/build_mysteries_book_note_rows_v1.py`
- `ela_pipeline/dataset/build_selected_book_note_rows_v2.py`

Output:

- one inventory table with:
  - source name
  - node type coverage
  - estimated quality
  - estimated transferable note count
  - extraction readiness

Stop/go:

- proceed only after we know which sources are worth projecting

### B. Build a canonical transferable note-unit pool

Goal:

- create one merged note-unit JSONL from all viable automatic sources

What a note unit means here:

- one extracted `notation + context` pair or one already normalized book-note row
- enough metadata to map it to a template family and projection level

Requirements:

- preserve provenance
- preserve source topic
- preserve node type
- preserve extracted note text
- preserve context text
- preserve risk flags

Output:

- `data/processed_note_units/transferable_note_units_v1.jsonl`

Target size:

- minimum `700`
- target `1000-1500`

Stop/go:

- if we cannot get past `700` high-quality units, then `25k` final rows is unlikely without broader source intake

### C. Template and slot-normalize the note-unit pool

Goal:

- convert raw book/dictionary note units into transferable templates

Primary scripts/modules:

- `ela_pipeline/dataset/template_slot_book_notes.py`
- `ela_pipeline/dataset/slot_normalize_projected_corpus.py`

Tasks:

1. repair unsafe slot substitutions
2. remove book-meta or chapter-reference notes
3. mark lexicalized notes that cannot transfer safely
4. retain only units that can be justified from structural evidence

Outputs:

- `transferable_note_units_templated_v1.jsonl`
- report with template coverage and rejection reasons

Acceptance:

- each retained unit must map cleanly to a template family or to a controlled passthrough class

### D. Choose and freeze the natural corpus base

Goal:

- define one canonical projection base for this experiment

Expected input:

- current best ingested natural corpus from the book projection workflow

Reference:

- `docs/book_intake_2026-03-18.md`

Tasks:

1. identify canonical corpus JSONL
2. confirm sentence count
3. confirm phrase-node count
4. confirm coverage of target families

Output:

- one documented projection base path

Stop/go:

- do not run multiple inconsistent corpus bases in parallel for the same experiment

### E. Project note packs onto the natural corpus

Goal:

- multiply a smaller note-unit pool into a large candidate set

Primary module:

- `ela_pipeline/dataset/project_template_notes_onto_corpus.py`

Tasks:

1. run projection per source pack
2. keep sentence-level and phrase-level projections separate in reports
3. measure candidates per note unit
4. inspect families with zero or very low projection yield

Outputs:

- one projected corpus per source pack
- one report per source pack

Metrics to record:

- note units in
- matched sentence rows
- matched phrase rows
- average candidates per note unit
- top families by yield
- families with poor yield

Acceptance:

- healthy projection multiplier should usually exceed `x15`

### F. Merge all projected corpora

Goal:

- combine multiple source projections into one candidate graph

Primary module:

- `ela_pipeline/dataset/merge_projected_book_corpora.py`

Tasks:

1. merge source projections incrementally
2. preserve candidate provenance
3. avoid duplicate candidates
4. keep merge reports at every step

Output:

- `merged_projected_corpus_v1.jsonl`

Acceptance:

- merged corpus must keep candidate diversity rather than collapse to one dominant source

### G. Run slot normalization on the merged projection

Goal:

- convert lexicalized borrowed notes into reusable structural candidates

Primary module:

- `ela_pipeline/dataset/slot_normalize_projected_corpus.py`

Tasks:

1. normalize preposition/object notes
2. normalize relative-clause marker notes
3. normalize tag-question notes
4. preserve original note text for audit
5. flag unresolved slot cases

Output:

- `merged_projected_corpus_slot_normalized_v1.jsonl`

Acceptance:

- unresolved slot-heavy families must be measured, not hidden

### H. Export train/dev/test from the projected corpus

Goal:

- turn the candidate graph into actual model rows

Primary module:

- `ela_pipeline/dataset/build_t5_dataset_from_projected_corpus.py`

Tasks:

1. use contract-template payload as model input
2. choose one target per eligible node
3. dedup exact pairs
4. cap repeated targets
5. split by source document to reduce leakage

Outputs:

- `train.jsonl`
- `dev.jsonl`
- `test.jsonl`
- `all.jsonl`
- build stats report

Acceptance:

- first strict export target is `10k-15k` rows
- second expansion target is `20k-25k+` rows

### I. Run QC before training

Goal:

- reduce silver-noise before model training

Primary module:

- `ela_pipeline/dataset/qc_dataset.py`

Tasks:

1. structural checks
2. semantic gate checks
3. OCR artifact rejection
4. lexical mismatch rejection
5. manual-review bucket for ambiguous rows

Outputs:

- `qc_report.csv`
- `clean.jsonl`

Acceptance:

- if retention after QC drops below `40%`, then projection quality or source quality is too weak

### J. Build a strict first training slice

Goal:

- train only on the cleanest structural-realization rows first

Tasks:

1. keep rows with low risk flags
2. keep rows with stable template compatibility
3. keep sentence/phrase/word balance
4. keep broad grammar-family coverage

Target size:

- first clean slice: `8k-15k`

Rationale:

- enough to test the architecture
- small enough to debug quickly

### K. Expand to the full training set

Goal:

- add controlled lexical-context rows after strict structural dataset is stable

Tasks:

1. add limited lexical cue families
2. re-run QC
3. rebalance over-represented families
4. keep strict eval sets unchanged

Target size:

- expanded dataset: `15k-25k+`

### L. Maintain a separate structural eval suite

Goal:

- verify the ELA claim rather than only generic note quality

Required eval groups:

1. same shape, different lexicon
2. different shape, similar lexicon
3. blueprint fidelity
4. fallback safety

Output:

- fixed eval pack checked on every retrain

## Time Estimate

### If the current source scripts are mostly usable

- source inventory and note-pack audit: `0.5-1.5` days
- canonical note-unit pool build: `1-2` days
- templating and slot-normalization fixes: `1-3` days
- projection + merge + reporting: `1-2` days
- export + QC + first strict dataset: `1-2` days

Estimated total to first usable `8k-15k` dataset:

- `4.5-10.5` working days

Estimated total to a stronger `15k-25k+` dataset:

- `7-14` working days

### If source quality is worse than expected

Main delay risks:

- extractors produce low-transfer notes
- projection yield is too low
- QC retention collapses
- phrase and word families are too lexicalized

In that case the duration can extend because the bottleneck becomes source cleanup, not pipeline plumbing.

## LLM Limit Assessment

This work is too large for one uninterrupted pass, but it is fully feasible across multiple sessions.

### What fits within normal working limits

- codebase audit
- TODO maintenance
- one pipeline slice at a time
- one or two builder/refactor patches per session
- one focused dataset stage per session

### What does not fit safely in one pass

- full source audit
- full projection build
- QC analysis
- runtime refactor
- training and evaluation

all in the same uninterrupted session

### Working rule

Treat this as a staged branch effort:

1. runtime correctness slice
2. dataset source inventory slice
3. note-unit pool build slice
4. projection and merge slice
5. QC/export slice
6. training/eval slice

This is exactly why this file exists: the context can be resumed safely between stops.

## Fast-Track Plan: Reduce Timeline By ~3x

If we need to compress the timeline by roughly three times, we must narrow scope aggressively.

### What changes in fast-track mode

We stop trying to solve the full dataset problem in one cycle.

Instead, we target:

- one strict dataset only
- sentence + phrase only
- top template families only
- already-ingested, already-usable sources only
- existing corpus base only
- minimal runtime fixes only where they directly unblock dataset validity

### Fast-track target

Deliver in the first cycle:

- `5k-8k` clean-enough rows
- sentence-level only
- focused on the highest-yield sentence families
- sufficient to validate the ELA structural-realization approach

Phrase and word notes are explicitly deferred to feedback-driven expansion.

Do not target `20k-25k+` in the first compressed cycle.

### What we explicitly cut

Cut for now:

- phrase-level automatic dataset expansion
- word-level automatic dataset expansion
- low-yield or noisy sources
- broad source inventory across every extractor
- new extractor development
- full template-family completeness
- deep manual QC review loops
- second-stage lexical-context dataset
- non-essential runtime architecture cleanup

### Fast-track source set

Use only the sources most likely to already yield transferable note units:

1. `build_cobuild_2011_book_note_rows_v1.py`
2. `build_mark_lester_book_note_rows_v1.py`
3. `build_azar_basic_book_note_rows_v1.py`
4. optionally `build_selected_book_note_rows_v2.py`

Ignore for the first fast-track cycle unless clearly needed:

- noisy OCR-first sources
- weak dictionary word-note sources
- anything requiring new extraction cleanup

### Fast-track family scope

Keep only top-yield sentence families already known to matter:

Sentence:

- `SENT_NEGATION_GENERAL`
- `SENT_NEGATION_DO_SUPPORT`
- `SENT_QUESTION_WH`
- `SENT_QUESTION_YES_NO_AUX`
- `SENT_QUESTION_YES_NO_DO_SUPPORT`
- `SENT_QUESTION_TAG`
- `SENT_EXISTENTIAL_THERE`
- `SENT_NOUN_CLAUSE_THAT`
- `SENT_PASSIVE_GENERAL`
- `SENT_CONDITIONAL_FIRST`
- `SENT_CONDITIONAL_SECOND`
- `SENT_IMPERATIVE`

Drop everything else for cycle 1.

### Fast-track build strategy

#### FT-1. Build one compact transferable note pool

Goal:

- `250-500` high-yield sentence note units only

Method:

- take only the prebuilt highest-quality book-note rows
- keep only sentence-level candidates
- do not spend time broadening source coverage yet

#### FT-2. Project onto one frozen corpus base

Goal:

- get raw candidate multiplier fast

Method:

- use the current canonical corpus base only
- no parallel corpus experiments

#### FT-3. Use hard filters instead of nuanced repair

Method:

- if a source/family is noisy, drop it
- if slot normalization is unsafe, drop it
- if template compatibility is weak, drop it

Bias toward precision over recall.

#### FT-4. Export one strict dataset only

Goal:

- `5k-8k` rows

Method:

- dedup aggressively
- cap repeated targets aggressively
- keep only low-risk candidates

### Fast-track runtime work

Only do the minimum runtime changes required to keep the dataset architecturally honest:

1. stop mutating `note_blueprints`
2. add note-quality gate with fallback

Defer for later:

- full contract-template runtime integration
- full telemetry expansion
- broader renderer refactor

### Fast-track timeline

If we stay disciplined about scope:

1. source subset + family subset lock: `0.5` day
2. compact note-pool build: `0.5-1` day
3. projection + merge: `0.5-1` day
4. hard-filter QC + export: `0.5-1` day
5. minimal runtime corrections: `0.5-1` day

Compressed first-cycle total:

- about `2.5-4.5` working days

### Fast-track success criteria

Cycle 1 is a success if we have:

- `5k-8k` rows
- sentence coverage only
- stable high-yield template families
- low lexical leakage
- same-shape/different-lexicon eval pack ready

Cycle 1 is not required to:

- solve phrase or word families automatically
- reach `25k+`
- fix all dataset sources
- complete the full runtime architecture migration

### Phrase/Word follow-up policy

For the next cycle:

- phrase notes should come from product feedback, error analysis, and manual high-value additions
- word notes should also come from feedback loops, not from broad automatic harvesting

This means:

- cycle 1 proves the sentence-layer ELA idea fast
- phrase/word work is guided by actual failure cases instead of large noisy extraction waves

## Evaluation Plan For The ELA Claim

We need tests that actually check the claim, not only generic generation quality.

### Eval 1. Same shape, different lexicon

For each target pattern:

- generate or collect several sentences with the same structural pattern
- vary nouns/verbs/content words
- require stable `grammar_classes`
- require semantically equivalent notes

### Eval 2. Different shape, similar lexicon

- keep similar vocabulary
- change the grammatical pattern
- require different note behavior

This checks that the model is tracking structure rather than content words.

### Eval 3. Blueprint fidelity

- compare rendered note to classifier-owned blueprint intent
- ensure wording can vary but pedagogical function does not drift

### Eval 4. Fallback safety

- inject bad generations
- verify blueprint fallback is used

## Oxford PEU Source Notes

Source checked on April 27, 2026:

- `/home/vlad/winshare/books/oxford-practical-english-usage-2005/Oxford Practical English Usage  (2005).pdf`
- the bundled `..._hocr_searchtext.txt.gz` is empty, so extraction must go through `pdftotext`

Artifacts created:

- `scripts/build_oxford_peu_sentence_rows.py`
- `data/processed_sentence_seed/oxford_peu_sentence_rows_v2.jsonl`
- `data/processed_sentence_seed/oxford_peu_sentence_rows_v2.report.json`
- `data/processed_sentence_seed/oxford_peu_sentence_pairs_v2.jsonl`
- `data/processed_sentence_seed/oxford_peu_sentence_pairs_v2.report.json`
- `data/processed_sentence_seed/oxford_peu_sentence_pairs_v2_clean_v1.jsonl`
- `data/processed_sentence_seed/oxford_peu_sentence_pairs_v2_clean_v2.jsonl`
- `data/processed_sentence_seed/oxford_peu_sentence_pairs_v2_clean_v2.report.json`

What worked:

- `Contents Overview` gives a clean manifest of entry numbers for sentence-relevant topics
- the book is structured enough to extract targeted entry windows automatically
- targeted sentence topics with useful yield:
  - `conditional_sentences`
  - `passive_voice`
  - `perfect`
  - `question_tags`
  - `relative_clauses`
  - `existential`

Current counts from this source:

- `78` Oxford entry windows
- `539` raw `notation -> context` pairs after handbook extraction
- `152` cleaner sentence-level pairs after strict filtering

Practical conclusion:

- this source is usable as a donor for the fast-track sentence pool
- it is not clean enough to treat raw extracted pairs as final train rows
- the clean subset should be merged as seed material, not as the entire cycle-1 dataset

Main extraction lesson:

- the introduction and overview pages are not train data
- they are useful for deriving the extraction order:
- `Contents Overview` -> choose entry ids
- targeted entry blocks -> build note/context rows
- strict clean filter -> keep only example-like sentence pairs

## Current Sentence Pair Pool

As of April 27, 2026, the merged book-derived sentence pair pool is:

- `data/processed_sentence_seed/book_sentence_pair_pool_v1.jsonl`
- `data/processed_sentence_seed/book_sentence_pair_pool_v1.report.json`

Current deduped totals:

- `751` sentence-level `notation -> context` rows
- `262` unique note texts
- `748` unique sentence contexts

Current source breakdown:

- Oxford PEU clean subset: `152`
- COBUILD 2011 first chapter subset: `182`
- COBUILD 2011 grammar chapter subset: `417`

Interpretation:

- the minimum fast-track note-unit quantity is now met
- the bottleneck is no longer raw source count
- the next bottleneck is balance and usefulness:
  - too many modal rows
  - too few progressive rows
  - some pronoun/adjective material is structurally valid but less central for cycle-1

Immediate next move from this state:

1. carve a cycle-1 projection/training subset from `book_sentence_pair_pool_v1`
2. bias toward:
   - `conditional_sentences`
   - `passive_voice`
   - `perfect`
   - `question_tags`
   - `relative_clauses`
   - `existential`
3. treat `modal`, `pronouns`, and `adjectives` as optional expansion layers rather than core cycle-1 signal

## Balanced Cycle-1 Pool Update

As of April 27, 2026 (later same branch), the pool was rebuilt into a more balanced `v2` set:

- `data/processed_sentence_seed/book_sentence_pair_pool_v2.jsonl`
- `data/processed_sentence_seed/book_sentence_pair_pool_v2.report.json`
- `data/processed_sentence_seed/cycle1_core_sentence_pair_pool_v2.jsonl`
- `data/processed_sentence_seed/cycle1_core_sentence_pair_pool_v2.report.json`
- `data/processed_sentence_seed/cycle1_expanded_sentence_pair_pool_v2.jsonl`
- `data/processed_sentence_seed/cycle1_expanded_sentence_pair_pool_v2.report.json`

New donor sources added into `v2`:

- `data/processed_sentence_seed/peter_simon_targeted_pairs_v2_clean.jsonl`
- `data/processed_sentence_seed/dummies_chapter3_progressive_pairs_v1_clean.jsonl`

New helper scripts:

- `scripts/extract_dummies_chapter3_rows.py`
- `scripts/build_cycle1_sentence_pair_pool.py`

What changed:

- `modal` is no longer allowed to dominate the expansion subset:
  - expanded `v2` caps `modal` at `60`
- `progressive` rows now go through an extra topic-specific QC check:
  - keep only contexts that actually contain a progressive verb pattern
- this intentionally drops noisy pseudo-progressive rows from Oxford and badly tokenized Peter Simon contexts

Current `v2` counts:

- merged pool: `795` rows
- merged topic counts:
  - `conditional_sentences`: `26`
  - `existential`: `32`
  - `passive_voice`: `45`
  - `perfect`: `56`
  - `progressive`: `8`
  - `question_tags`: `32`
  - `relative_clauses`: `42`
  - `modal`: `372`
  - `adjectives`: `88`
  - `pronouns`: `93`
- core subset: `241` rows
- expanded balanced subset: `301` rows

Important interpretation:

- balance is now materially better than `v1`
- the remaining weak topic is still `progressive`
- however, the weak point is now source quality, not missing plumbing:
  - Oxford `progressive` rows are mostly about verbs that do *not* take progressive forms
  - Peter Simon `progressive` yield is low because of text-tokenization damage
  - Geraldine Woods chapter 3 is currently the cleanest progressive donor

Recommended next move from this exact state:

1. keep `cycle1_core_sentence_pair_pool_v2` as the main sentence-only cycle-1 set
2. use `cycle1_expanded_sentence_pair_pool_v2` only as an optional expansion layer
3. if more `progressive` is needed, mine another clean EPUB chapter rather than relaxing the strict topic QC

## Book-Adapter Expansion Update

As of April 28, 2026, the sentence pool was extended with book-specific adapters instead of another generic scrape pass.

New adapters added:

- `scripts/build_geraldine2010_targeted_pairs.py`
- `scripts/build_cobuild_c04_tense_pairs.py`

New clean sources added:

- `data/processed_sentence_seed/geraldine2010_targeted_pairs_v1_clean.jsonl`
- `data/processed_sentence_seed/cobuild_c04_tense_pairs_v1_clean.jsonl`

What these adapters do:

- `geraldine2010_targeted_pairs_v1_clean`
  - mines only two controlled areas from `Geraldine Woods - English Grammar For Dummies - 2010.epub`
  - `passive_voice`: section `a2`
  - `existential`: sections `a5` and `a12`
  - keeps only example-like lines, not explanation prose
- `cobuild_c04_tense_pairs_v1_clean`
  - mines chapter `OEBPS/c04.htm` from `Collins Cobuild English Grammar - 2011.epub`
  - targets:
    - present progressive
    - past progressive
    - present perfect / present perfect progressive continuation
    - past perfect progressive
  - keeps only sentence-level examples that actually match progressive/perfect regex filters
  - excludes question-form noise and truncated abbreviations

Current best merged/core/expanded outputs from this state:

- `data/processed_sentence_seed/book_sentence_pair_pool_v11.jsonl`
- `data/processed_sentence_seed/book_sentence_pair_pool_v11.report.json`
- `data/processed_sentence_seed/cycle1_core_sentence_pair_pool_v11.jsonl`
- `data/processed_sentence_seed/cycle1_core_sentence_pair_pool_v11.report.json`
- `data/processed_sentence_seed/cycle1_expanded_sentence_pair_pool_v11.jsonl`
- `data/processed_sentence_seed/cycle1_expanded_sentence_pair_pool_v11.report.json`

Current `v11` counts:

- merged pool: `725`
- core subset: `178`
- expanded subset: `238`

Current `v11` core topic counts:

- `conditional_sentences`: `22`
- `existential`: `21`
- `passive_voice`: `28`
- `perfect`: `40`
- `progressive`: `18`
- `question_tags`: `21`
- `relative_clauses`: `28`

Important interpretation:

- the new COBUILD `c04` adapter is the first donor that materially moved `progressive`
- `progressive` is no longer critically underrepresented, but it is still the smallest major topic
- `perfect` also improved noticeably without loosening QC
- this confirms the current strategy:
  - mine structured EPUB chapters with book-specific adapters
  - prefer section-aware extraction over generic note/context harvesting

Recommended next move from this exact state:

1. continue with the same adapter pattern on another clean EPUB chapter, not a generic book-wide pass
2. prioritize any source that can still raise:
   - `progressive`
   - `existential`
   - `question_tags`
3. if forced to choose between more rows and cleaner rows, keep the stricter row quality

## Resume Protocol

When resuming this branch:

1. read this file first
2. inspect current diff in:
   - `ela_pipeline/inference/run.py`
   - `ela_pipeline/annotate/controlled_renderer.py`
   - `ela_pipeline/annotate/contract_template_builder.py`
   - `ela_pipeline/validation/notes_quality.py`
   - `ela_pipeline/dataset/template_slot_book_notes.py`
   - `ela_pipeline/dataset/build_t5_dataset_v22_book_pairs.py`
   - `ela_pipeline/training/train_generator.py`
3. verify whether the current subtask is runtime or dataset work
4. do not mix runtime refactor and dataset cleanup in one patch unless the dependency is direct
5. before editing, re-check that ownership boundaries still match `docs/contract_field_ownership_2026-03-04.md`

## First Concrete Implementation Slice

Recommended next coding slice:

1. patch `run.py` so T5 output no longer mutates `note_blueprints`
2. add render trace fields
3. add runtime `is_valid_note()` gate with fallback to blueprint text
4. add focused tests for the controlled path

Why first:

- this fixes the most important production correctness issue
- it narrows the architecture before changing dataset assumptions

## Second Concrete Implementation Slice

1. wire `contract_template_builder` into controlled runtime
2. update renderer interface
3. add template-payload persistence

## Third Concrete Implementation Slice

1. tighten dataset slot parametrization
2. build first strict structural realization dataset
3. retrain renderer on strict dataset
4. run same-shape/different-lexicon eval

## Non-Goals While This File Is Active

- do not reintroduce free-form full-contract T5 generation
- do not let dataset convenience override ownership boundaries
- do not treat blueprint wording and rendered wording as the same layer
- do not claim lexical invariance until the dedicated evals pass
