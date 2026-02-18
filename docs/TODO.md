# TODO

## Working Environment Notes

- [x] Use project virtualenv for all commands: prefer `.venv/bin/python -m ...` (or `.venv/bin/pip ...`), avoid plain `python`.

## License Compliance Workflow

- [x] Define GPL policy for planned phonetics stack in `docs/licenses_inventory.md` (backend-only allowed, distributed delivery requires legal gate).
- [x] Add pre-merge checklist item: every new dependency/model must include license entry + deployment mode note.
- [x] Add release checklist item: block on-prem/distributed releases until license-compliance review is marked passed.
  - [x] Checklists documented in `docs/license_compliance_checklists.md`.

## Contract v2 Improvements

- [x] Enforce phrase shaping constraints:
  - [x] simple determiner-led noun chunks may be filtered by builder heuristics (e.g., `the decision`)
  - [x] contract allows mixed children for `Sentence` and `Phrase` nodes (`Phrase|Word`)
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

## Review Follow-ups (High Priority)

- [x] Replace string sentinel values (`\"null\"`) with real `null` in strict schema and pipeline outputs for `tense/aspect/mood/voice/finiteness`.
- [x] Keep backward compatibility for legacy mode while migrating strict mode to real nulls.
- [x] Fix TAM classification for modal perfect constructions (`should/could/might have + VBN`) so they are not labeled as `past perfect`.
- [x] Add explicit modal-perfect representation (for example `mood=modal`, `aspect=perfect`, `tense=null`, plus dedicated construction label).
- [x] Update strict schema and validator rules to reflect the modal-perfect and real-null policy.
- [x] Add regression tests covering `had + VBN` vs `should have + VBN` distinction.
- [x] Update dataset building to train only on notes with `source=\"model\"` and exclude fallback notes from targets.
- [x] Ensure training targets exclude telemetry fields (`quality_flags`, `reason_codes`, `rejected_*`) and contain only note text fields.

## v2_strict Finalization (P0)

- [x] Set `mood="modal"` for modal auxiliary word nodes (e.g., `should/could/might`), keeping node-level consistency with `tam_construction=modal_perfect`.
- [x] Normalize `features` null sentinels to real JSON `null` in `v2_strict` outputs (never string `"null"` in strict mode).
- [x] Update strict validation/schema to accept `features` values as `string|null` and reject string sentinel `"null"` in strict mode.
- [x] Add/refresh regression tests for strict-mode feature null normalization and modal auxiliary mood consistency.

## T5-small Fine-tuning Backlog

- [x] Build clean train/dev splits from `notes` where `source="model"` only (exclude fallback/telemetry fields).
- [x] Enforce note target style normalization (1-2 sentences, remove generic/template artifacts).
- [x] Balance training samples by node type (`Word/Phrase/Sentence`) and TAM construction buckets.
- [x] Freeze prompt template format for reproducible T5 training input.
- [x] Add reproducible baseline training config + evaluation report artifacts.
- [x] Add hard-negative loop from `rejected_candidates` to improve note quality filters.

## Rejected Candidates Cleanup (TZ 2026-02-13)

- [x] Implement deterministic filtering and canonical normalization for `rejected_candidates` and `rejected_candidate_stats`.
- [x] Add configurable stop-substrings/regex + sentence-prefix whitelist policy in pipeline code.
- [x] Add unit tests for filtering, whitelist behavior, normalization, deduplication, stats aggregation, length and nonalpha thresholds.
- [x] Extend sentence-prefix filtering to catch `Sentence ...` without colon and typo-leading variants (`sentense/sensence/sensibilisation`).
- [x] Apply the same blocklist/quality pre-filter to model note acceptance to prevent low-quality `MODEL_NOTE_ACCEPTED` outputs.

## Rejected Candidates v3 (TZ 2026-02-13)

- [x] Implement v3 normalization pipeline for candidates/stats text (`trim`, whitespace collapse, punctuation spacing, trailing punctuation normalization, deterministic `norm_key`).
- [x] Implement v3 stop-list filtering with configurable patterns (`sensibilisation|sensibilization|sensence|nod to|none. node content|node content|persona|must.*use|does not.*use`).
- [x] Implement `Sentence:` default-drop policy with config-driven allowlist (`allowlist_sentence_templates`).
- [x] Implement short-string policy (`min_len=5`) with config-driven `allowlist_short_tokens`.
- [x] Ensure stable deduplication for `rejected_candidates` and grouped aggregation for `rejected_candidate_stats` (`count` sum, unique sorted `reasons`).
- [x] Add/refresh unit tests for v3 acceptance criteria (stop-list, `Sentence:` policy, normalization dedup, stats merge, determinism).

## Rejected Candidates v3 Follow-up (Review 2026-02-13)

- [x] Extend sentence-drop rule from only `Sentence:` to sentence-like meta openings (`^senten(?:ce|se)\\b`) with allowlist override.
- [x] Extend stop-list with observed noisy variant `sensational` and meta patterns (`node type`, `part of speech`) for rejected-candidate filtering.
- [x] Add regression tests for new noisy patterns from latest inference sample (`Sensational ...`, `Sentence is ...`, `Sentence in ...`, `Sentence was ...`).

## Semantic Sanity Checks (Review 2026-02-13)

- [x] Add rule-based semantic sanity checks for candidate text using node context (`part_of_speech`, phrase content).
- [x] For `prepositional phrase` nodes with temporal heads (`before/after`), drop or mark candidates that label them as `concession`/`reason`.
- [x] Apply sanity checks both in note suitability gate and rejected-candidate normalization path to keep diagnostics clean.
- [x] Add regression tests for semantic mismatch cases (e.g., `before + V-ing` incorrectly labeled as `subordinate clause of concession/reason`).

## Rejected Candidates Noise Expansion (Review 2026-02-13)

- [x] Expand stop-list with newly observed noisy variants from latest inference output (`sensibilite`, `sensibilität`) and cover them with regression tests.

## Dataset + Training Refresh (Review 2026-02-13)

- [x] Add compatibility layer in dataset builder for legacy `targets.linguistic_notes` and current `notes[{text, source}]` schemas (single unified extraction path).
- [x] Add explicit dataset schema detection + fail-fast diagnostics (stop run if extracted rows are zero or schema mismatch is detected).
- [x] Regenerate `data/processed/{train,dev,test}.jsonl` from a single canonical source using current builder and save fresh `stats.json` with level/TAM distributions.
- [x] Add target dedup controls for training data (global dedup by normalized target + configurable max examples per identical target string).
- [x] Add low-quality target filters for legacy template artifacts (`verb-centred ...`, `subordinate clause of concession ...`, similar generic templates).
- [x] Extend `stats.json` with quality counters (unique target count, duplicate ratio, top repeated targets) to prevent silent dataset collapse.
- [x] Update training entrypoint to validate processed dataset freshness/compatibility before training starts (block on stale or incompatible JSONL format).
- [x] Retrain baseline `t5-small` on refreshed dataset and save comparable `evaluation_report.json` before/after refresh.
- [x] Run regression inference suite on fixed probe sentences and document quality delta in `docs/` (accepted-note rate, fallback rate, key error classes).

## Inference Noise Loop (Review 2026-02-13, 16:51)

- [x] Expand rejected-candidate stop-list for prompt-leak noise observed in latest inference (`in English`, `natural English`, `booleans/JSON fragments`, repetitive `Noun. Noun...` patterns).
- [x] Add structural heuristic to drop repetition-heavy candidates (low unique-token ratio / repeated POS-token spam).
- [x] Add regression tests for new prompt-leak and repetition-noise patterns.
- [x] Re-run inference probe and verify cleaned `rejected_candidates` while preserving valid diagnostics.

## Reference-Based Dataset (Network Sources)

- [x] Collect authoritative English grammar references (Cambridge, Oxford, Merriam-Webster, Purdue OWL, British Council, etc.) and save a source registry with links.
- [x] Build a normalized grammar concept inventory (POS roles, clause types, TAM patterns, dependency-role phrasing) from the references.
- [x] Add deterministic target-template library derived from the concept inventory (multiple high-quality variants per concept).
- [x] Generate refreshed training targets using reference-backed templates with diversity constraints (per POS, per level, per pattern caps).
- [x] Rebuild processed dataset and verify quality gates (`duplicate_ratio`, `top_20_target_share`, coverage by level/POS/TAM buckets).
- [x] Retrain `t5-small` on the reference-backed dataset and compare regression metrics against current baseline.
- [x] Document source list, derivation rules, and before/after metrics in `docs/`.

## Template-ID Dataset Mode (T5-small)

- [x] Add strict template-id mapping for Sentence/Phrase/Word nodes (fixed template library, no dynamic IDs).
- [x] Add dataset builder mode that emits `target = template_id|note` with short, low-variance notes (<=30 words, 1 sentence preferred).
- [x] Enforce hard target rules in builder (no banned prefixes/tokens/placeholders; feature-consistent notes only).
- [x] Wire template-id mode into `iter_examples` and CLI flags (`--use-template-id-targets`) with deterministic priority over raw notes/reference templates.
- [x] Extend dataset stats with template-id coverage/distribution and template-target quality counters.
- [x] Add unit tests for template-id target generation, hard-rule compliance, and CLI mode behavior.
- [x] Rebuild processed dataset in template-id mode and compare diversity/quality stats to current reference dataset.
- [x] Retrain `t5-small` on template-id dataset and compare regression metrics (`accepted_note_rate`, `fallback_rate`, `rejected_nodes_total`).
  - [x] Retrain `t5-small` on `data/processed_template_id` and store metrics artifact.
  - [x] Run stable regression inference comparison (`accepted_note_rate`, `fallback_rate`, `rejected_nodes_total`) for template-id model vs refreshed baseline.
- [x] Document template-id experiment results in `docs/`.

## Inference Runtime Policy

- [x] Enforce GPU-only inference for local T5 annotator (no silent CPU fallback).
- [x] Return explicit runtime error when CUDA is unavailable during inference with `--model-dir`.

## Hybrid Template + RAG (Next Iteration)

### P0 (must-have)

- [x] Define canonical context key and hierarchical matching policy (`L1 exact`, `L2 drop TAM`, `L3 level+POS`, `L4 level fallback`).
- [x] Implement canonical context-key builder in runtime (`level|pos|dep|tam|lex`) with deterministic normalized keys and trace payload.
- [x] Add hierarchical selector that searches registry in order `L1 -> L2 -> L3 -> L4` and logs matched key per node.
- [x] Build versioned template registry v1 with deterministic rules and 5-15 note variants per active template.
- [x] Expand registry entries for active node families (Sentence/Phrase/Word) to raise non-fallback coverage on real inference probes.
- [x] Implement deterministic selector (`template_only`) in inference pipeline with selection trace logging.
- [x] Add dataset quality gates that block training when diversity collapses (`min_unique_targets`, `max_top1_share`, `min_active_template_ids`).
- [x] Add regression report with required KPIs: `accepted_note_rate`, `fallback_rate`, `rejected_nodes_total`, `L1-L4 coverage`.

### P1 (should-have)

- [x] Curate licensed source list for large-scale data ingestion (target: 3k sentences / 9k phrases / 18k words) with explicit allow/deny policy per source.
- [x] Build source ingestion plan for target scale (3000 sentence / 9000 phrase / 18000 word) with per-source quotas and license metadata requirements.
- [x] Implement corpus ingestion script(s) that export normalized JSONL with provenance fields (`source_name`, `source_url`, `license`, `collected_at`).
- [x] Add extraction pipeline to derive phrase/word records from ingested sentences via spaCy parse and deterministic context-key mapping.
- [x] Add ingestion QA report (license coverage, parse success rate, duplicate ratio, POS/dep/TAM distribution, per-source contribution).
- [x] Regenerate template-id training dataset from ingested corpus and run quality gates before training.
- [x] Run end-to-end dataset refresh strictly via ingestion chain (`raw_sources` -> `build_ingestion_corpus` -> `extract_ingested_nodes` -> QA) for the new corpus only.
- [x] Run GPU-only retraining + regression inference QC on refreshed dataset and publish comparison report vs current baseline.
  - [x] Interim checkpoint-level QC comparison published (`docs/reports/2026-02-13/inference_qc_compare_ingested_checkpoint800_vs_baseline_2026-02-13.json`).
  - [x] Finalize full-run `best_model` QC comparison after training completion.
- [x] Add template semantic compatibility rules (`template_id` vs POS/dep/TAM/content) and reject incompatible matches before note emit.
- [x] Add semantic mismatch metric to QC report and make it a regression gate.
- [x] Expand registry mappings for top unresolved contexts from latest QC to reduce `L4` without semantic degradation.

### P2 (nice-to-have)


## Note Quality Hardening (Current)

- [x] Zero irrelevant TAM fields for NP/PP/Word nodes (keep only context-relevant grammatical dimensions).
- [x] Enforce deterministic `note.kind` mapping by template family (`SENTENCE_*`, `PHRASE_*`, `WORD_*`).
- [x] Replace generic sentence note for `modal_perfect` with TAM-informative explanation text.
- [x] Switch inference pipeline to two-stage mode: `model predicts template_id` -> `rule engine renders note text`.
- [x] Standardize two-stage telemetry: `selection_mode`, non-contradictory `quality_flags/reason_codes`, and single terminal reason code.
- [x] Enforce template-only diagnostics in two-stage rejections (no free-form text in `rejected_candidates`).
- [x] Add rule-priority in `two_stage` (`L1/L2` rule match skips model call) to avoid noisy model rejections.

## Two-Stage Logging + Structure Hardening (Review 2026-02-14)

- [x] Align `selection_mode` with matched level (`rule_l1_exact`, `rule_l2_drop_tam`, `rule_l3_backoff`).
- [x] Add `context_key_matched` into `template_selection` trace to make selected context explicit.
- [x] Normalize duplicate span nodes with `ref_node_id` links (keep canonical node + mark duplicate references).
- [x] Emit `matched_level_reason="tam_dropped"` only for TAM-relevant node families.
- [x] Add validator guard: `matched_level_reason="tam_dropped"` allowed only for TAM-relevant nodes.
- [x] Add `quality_flags=["backoff_used"]` when template selection level is not `L1_EXACT`.
- [x] Add QC aggregate metrics: `backoff_rate` and `tam_drop_rate`.
- [x] Codify validator contract for `backoff_used` consistency with `template_selection.level`.
- [x] Document trace semantics: `context_key_matched` as source of truth, `tam_construction` as separate TAM channel.
- [x] Add sentence-level `backoff_nodes_count` for quick backoff diagnostics in large trees.
- [x] Add optional debug `backoff_summary` (`nodes`, `reasons`) behind CLI flag `--backoff-debug-summary`.
- [x] Document and test sentence-level backoff diagnostics fields.
- [x] Formalize counting contract: `backoff_nodes_count` includes sentence node; add explicit `backoff_leaf_nodes_count`.
- [x] Extend debug summary with `leaf_nodes` for direct leaf-level audit.
- [x] Clarify contract that `backoff_leaf_nodes_count` is node-based (duplicates by span are allowed).
- [x] Add `backoff_unique_spans_count` for deduplicated span-level backoff metric.
- [x] Add explicit `backoff_aggregate_nodes_count` to separate aggregate-node effects from leaf-node effects.
- [x] Formalize aggregate counting policy: sentence aggregate backoff is own-level only (`template_selection.level != L1_EXACT`).
- [x] Add validator consistency checks for backoff counters (`nodes = leaf + aggregate`, `unique_spans <= leaf`).
- [x] Add node-level aggregate signal `backoff_in_subtree` (descendant backoff only) without changing `backoff_used` local semantics.
- [x] Add validator checks for `backoff_in_subtree` consistency with descendant signals.
- [x] Document local vs subtree backoff semantics to avoid metric drift.
- [x] Document `dep_label` semantics as source-parse dependency label (not phrase-internal dependency role).
- [x] Enforce node serialization order with `linguistic_elements` as the last field for `Sentence`/`Phrase`/`Word`.

## Documentation Hygiene

- [x] Consolidate template-id experiment narrative into one canonical report (`docs/template_id_experiment_report_2026-02-13.md`).
- [x] Remove intermediate duplicate reports and keep only primary regression artifact + consolidated summary.
- [x] Add consolidated tool/model/data license inventory with explicit allowed MT model (`facebook/m2m100_418M`, MIT).

## Multilingual Translation Rollout

- [x] Add multilingual translation stage scaffold in inference pipeline with provider interface.
- [x] Integrate `m2m100` provider (`facebook/m2m100_418M`, MIT) with CLI controls (`--translate`, source/target language, device).
- [x] Add project-local model bootstrap command (`.venv/bin/python -m ela_pipeline.translate.prepare_m2m100`) and auto-resolve local `artifacts/models/m2m100_418M` for default translation runs.
- [x] Emit translation payload into output JSON at sentence level and optional node level.
- [x] Add alignment-aware phrase/word translation projection (source-span/ref-node based, with deduplicated translation calls).
- [x] Add translation quality regression suite (EN->RU first, then extend language pairs).
- [x] Add translation-field validation contract in strict mode.

## Phonetic Transcription Rollout (EN, UK/US)

- [x] Define contract extension for phonetics on all node levels (`Sentence`, `Phrase`, `Word`):
  - [x] `phonetic.uk` (IPA-like UK pronunciation)
  - [x] `phonetic.us` (IPA-like US pronunciation)
  - [x] Keep `linguistic_elements` as the final field after phonetic enrichment.
- [x] Add CLI controls for optional phonetic enrichment (`--phonetic`, provider/binary, node toggle).
- [x] Introduce phonetic provider interface and first implementation for EN UK/US output.
- [x] Add source-span/ref-node aware deduplication for phonetic generation (reuse by `ref_node_id` and normalized text).
- [x] Add strict validator rules for `phonetic` fields in `v2_strict` (shape/types/non-empty constraints).
- [x] Add TDD regression tests:
  - [x] sentence/phrase/word phonetic payload presence,
  - [x] UK/US pair consistency,
  - [x] dedup behavior for duplicate spans/ref nodes,
  - [x] serialization order invariant (`linguistic_elements` last).
- [x] Add phonetic quality-control script/report (smoke set + structural checks).
- [x] Document phonetic stage in sample contract (`docs/sample.json`).
- [x] Add final license gate before production enablement of chosen phonetic backend (per `docs/licenses_inventory.md`).
  - [x] Added gate module/CLI: `ela_pipeline/runtime/license_gate.py`.
  - [x] Added checklist command in `docs/license_compliance_checklists.md`.
  - [x] Added tests: `tests/test_runtime_license_gate.py`.

## Synonyms Rollout (EN, WordNet)

- [x] Define contract extension for synonyms on node levels using `synonyms: [string, ...]`.
- [x] Add CLI controls for optional synonym enrichment (`--synonyms`, provider, top-k, node toggle).
- [x] Introduce synonym provider interface and first implementation (`wordnet` via NLTK).
- [x] Add source-span/ref-node aware deduplication for synonym generation (reuse by `ref_node_id` and normalized source key).
- [x] Add context-aware synonym post-processing for verbs (phrasal expansion + participle-form alignment) to reduce out-of-context lemmas.
- [x] Add validator rules for optional `synonyms` fields:
  - [x] unique non-empty strings when present,
  - [x] allow empty list for function-word nodes,
  - [x] require non-empty list for content-word nodes (`noun|verb|adjective|adverb`).
- [x] Add TDD regression tests for synonym enrichment + validator checks.
- [x] Document WordNet prerequisite (`nltk.downloader wordnet omw-1.4`) in docs.

## CEFR Rollout

- [x] Fix canonical CEFR corpus file in repository root: `linguistic_hierarchical_3000_v5_cefr_balanced.json`.
- [x] Switch dataset builders to canonical CEFR corpus by default (`build_dataset --input` default -> `linguistic_hierarchical_3000_v5_cefr_balanced.json`).
- [x] Add fail-fast CEFR corpus validation before CEFR dataset build (`--task cefr_level`).
- [x] Define contract extension for CEFR on node levels (`Sentence`, `Phrase`, `Word`) with optional `cefr_level`.
- [x] Add validator rules for `cefr_level` with allowed labels only: `A1|A2|B1|B2|C1|C2`.
- [x] Add CLI controls for optional CEFR enrichment (`--cefr`, model path, node toggle).
- [x] Implement CEFR feature extractor based on current contract fields (no legacy schema assumptions).
- [x] Integrate CEFR prediction stage into inference pipeline with fail-fast model loading for `ml` provider.
- [x] Extend corpus dataset builder with CEFR mode (`ela_pipeline.dataset.build_dataset --task cefr_level`) to rebuild train/dev/test from CEFR-annotated hierarchical corpus.
- [x] Rebuild CEFR dataset splits from updated corpus (`data/processed_cefr*`) through the standard dataset pipeline.
- [x] Add CEFR quality-control script (coverage + class distribution + sanity checks).
- [x] Publish CEFR quality-control report artifact in `docs/reports/`.
  - [x] `docs/reports/cefr_qc_2026-02-17_13-30-05.json` (T5 provider, anomaly_rate=0.0).
- [x] Add TDD regression tests for CEFR stage (sentence/phrase/word, ordering invariants, deterministic behavior).
- [x] Document CEFR stage in README/CLI/full docs/sample contract.

## DB Persistence (In Progress, Postgres-only)

- [x] Document decision: PostgreSQL is primary storage (no MongoDB in current architecture).
- [x] Add deterministic `sentence_key` for sentence-level identity.
- [x] Define and document `canonical_text` normalization (trim, whitespace collapse, Unicode NFC).
- [x] Add `hash_version` (for example `v1`) for key schema evolution.
- [x] Implement key formula: `sha256(canonical_text + source_lang + target_lang + pipeline/model context)`.
- [x] Add `UNIQUE` index on `sentence_key`.
- [x] Design minimal PostgreSQL schema: `runs`, `sentences` (contract in `jsonb`).
- [x] Store full pipeline contract payload in `jsonb`.
- [x] Promote analytics-critical fields to columns (`tam_construction`, `backoff_*`, `language_pair`, etc.).
- [x] Add DB migrations for schema creation and upgrades.
- [x] Add repository/DAO layer for write path.
- [x] Implement idempotent upsert by `sentence_key` (`ON CONFLICT` flow).
- [x] Add DB integration tests (TDD): insert, dedup, query by metrics.
  - [x] Real PostgreSQL integration test added: `tests/test_db_integration_postgres.py`.
- [x] Optional later: add Redis cache for translation hot-path.
  - [x] Added optional translation cache backends (`memory|redis`) with env-driven bootstrap in `ela_pipeline/translate/cache.py`.
  - [x] Wired translation stage to cache reads/writes in inference (`_attach_translation`, `run_pipeline`).
  - [x] Added tests for cache key/env bootstrap + translation cache reuse.

## Deployment (Docker)

- [x] Add container image definition for app runtime (`Dockerfile`).
- [x] Add `docker-compose.yml` for `app + postgres` with persistent volumes and healthcheck.
- [x] Add env template for deployment (`.env.example`).
- [x] Add startup DB migration command for container flow (`ela_pipeline.db.migrate`).
- [x] Document docker deployment runbook (`docs/deploy_docker.md`).
- [x] Migrate runtime commands to Docker Compose v2 (`docker compose`), remove legacy v1 binary.

## Long-Term Backlog (Far Future)

- [x] Introduce dual translation channels in contract:
  - [x] `translation_literary` (baseline from `m2m100`)
  - [x] `translation_idiomatic` (rule-based rewrite layer with literary fallback)
  - [x] Keep both as top-level sibling fields per node (no nested alternatives array).
  - [x] Backward-compatible `translation` field is retained.

## Human-in-the-Loop Corrections (Planned)

- [x] Add editable-review schema for key fields in contract (`notes`, `translation`, `phonetic`, `synonyms`, `cefr_level`, critical grammar tags).
  - [x] Added schema module: `ela_pipeline/hil/review_schema.py`.
  - [x] Added dynamic field-path validation by root (`notes[0].text`, `translation.text`, `phonetic.uk`, etc.).
  - [x] Integrated schema checks in feedback quality gates (`ela_pipeline/hil/export_feedback.py`).
  - [x] Added tests: `tests/test_hil_review_schema.py` + updated `tests/test_hil_repository.py`.
  - [x] Persistence base added: `review_events` + `node_edits` tables for sentence/node-level corrections.
- [x] Add reviewer metadata model (`reviewed_by`, `reviewed_at`, `change_reason`, `confidence`) on every manual correction.
- [x] Implement diff logger that stores `before/after` for every corrected node field.
- [x] Build correction export pipeline: accepted edits -> normalized feedback dataset (JSONL) for retraining.
- [x] Add dataset quality gates for human-feedback export (dedup, invalid-label filter, license/provenance consistency).
  - [x] Dedup gate added (`sentence_key + node_id + field_path + after_value`).
  - [x] Invalid-label/field filter added (`cefr_level` allowed set + `field_path` whitelist).
  - [x] License/provenance consistency gate added (`source/license` matrix + required `source_url` for external-attributed licenses).
- [x] Add training pipeline mode to mix base corpus + human-feedback dataset with configurable weighting.
  - [x] Initial implementation in trainer CLI: `--feedback-train` + `--feedback-weight`.
- [x] Add regression checks proving that model quality improves after feedback retraining and does not break contract validity.
  - [x] Added gate CLI: `ela_pipeline.training.feedback_regression` (compares train metrics + inference QC and fails on degradation).

## Next Stage: Productization (Client-First, Offline-First)

- [x] Fix and document next-stage product scope in `docs/next_stage_product_spec_2026-02-17.md`.
- [x] Fix legacy feature source mapping (`feature -> source project -> source files`) in `docs/legacy_feature_source_map_2026-02-17.md`.
- [ ] Reuse ELA `main_menu` UX as canonical navigation baseline (no full redesign from scratch).
- [x] Build frontend migration map screen-by-screen (`Projects -> Files -> Analyze -> Vocabulary`) and bind to current backend contracts.
  - [x] Documented in `docs/ui_migration_map_2026-02-17.md`.
- [x] Implement local client persistence (SQLite) for projects/files/local edits/workspace state.
  - [x] Added `ela_pipeline/client_storage/sqlite_repository.py`.
  - [x] Added unit tests `tests/test_client_sqlite_repository.py`.
- [ ] Define and implement offline/online capability matrix in runtime + UI (feature flags and graceful degradation).
  - [x] Runtime policy layer added (`ela_pipeline/runtime/capabilities.py`) with fail-fast checks for offline disallowed features.
  - [x] Inference CLI wired with `--runtime-mode auto|offline|online` + `ELA_RUNTIME_MODE`.
  - [x] UI state contract added (`ela_pipeline/runtime/ui_state.py`):
    - [x] capability badges payload (`build_runtime_ui_state`)
    - [x] disabled-state reasons for blocked features
    - [x] fallback messaging payload for local/backend/reject (`build_submission_ui_feedback`)
  - [x] Frontend integration service added (`ela_pipeline/runtime/service.py`) to expose UI-ready payloads and submission flow.
  - [x] Visual UI components to render this payload in frontend screens.
    - [x] React component `RuntimeStatusCard` added (badges + disabled reasons).
    - [x] React page `AnalyzePage` renders runtime payload + feedback block.
- [ ] Enforce media routing policy:
  - [x] Runtime policy engine added (`ela_pipeline/runtime/media_policy.py`) with decision routes: `local|backend|reject`.
  - [x] local processing for files <= 15 minutes (policy decision path implemented).
  - [x] backend async job path for files > 15 minutes (policy decision path implemented, requires backend_jobs capability).
  - [x] Backend orchestration base added:
    - [x] `ela_pipeline/runtime/media_orchestrator.py` (execution plan: `run_local|enqueue_backend|reject`)
    - [x] local SQLite backend job queue in `ela_pipeline/client_storage/sqlite_repository.py` (`backend_jobs` table + CRUD methods)
    - [x] submission helper added: `ela_pipeline/runtime/media_submission.py` (single entrypoint for Start action)
  - [x] UI payload adapters added for route/status and user-facing messages (`ela_pipeline/runtime/ui_state.py`).
  - [x] Service-level wiring for Start action added (`RuntimeMediaService.submit_media`).
  - [x] Visual UI wiring to consume orchestration payload and show route/status in interface.
    - [x] React `MediaSubmitForm` wired to API submit.
    - [x] UI feedback severity/title/message rendered from `ui_feedback`.
    - [x] Backend job list rendered in `BackendJobsTable`.
- [ ] Add media file size limits for both paths (configurable env/runtime thresholds):
  - [x] reject local jobs above `MEDIA_MAX_SIZE_LOCAL_MB` (policy routes to backend/reject).
  - [x] reject backend jobs above `MEDIA_MAX_SIZE_BACKEND_MB`.
  - [x] fail-fast validation message includes actual duration/size and active limits.
  - [x] CLI validation hook added in inference runner (`--media-duration-sec` + `--media-size-bytes`).
- [x] Implement backend temporary media retention policy (TTL cleanup, no permanent storage of user final media).
  - [x] Added runtime cleanup module: `ela_pipeline/runtime/media_retention.py`.
  - [x] Added CLI: `python -m ela_pipeline.runtime.cleanup_media_tmp` (`--dry-run` supported).
  - [x] Added env config: `MEDIA_TEMP_DIR`, `MEDIA_RETENTION_TTL_HOURS`.
  - [x] Added tests: `tests/test_runtime_media_retention.py`.
- [x] Enforce minimal backend identity policy (phone-linked account only, no extra PII by default).
  - [x] Added phone normalization/hash policy module: `ela_pipeline/identity/policy.py`.
  - [x] Added DB migration/table for hash-only accounts: `ela_pipeline/db/migrations/0004_backend_accounts.sql` (`backend_accounts.phone_hash`).
  - [x] Added repository methods: `upsert_backend_account` / `get_backend_account_by_phone_hash`.
  - [x] Added tests: `tests/test_identity_policy.py`, `tests/test_db_backend_accounts.py`.
- [x] Add sync flow for user-submitted new content that is missing from shared corpus.
  - [x] Added local sync queue in SQLite: `sync_requests` table.
  - [x] Added repository methods: enqueue/list/update status for sync requests.
  - [x] Added service layer: `ela_pipeline/runtime/sync_service.py`.
  - [x] Added tests: `tests/test_runtime_sync_service.py` (+ repository coverage in `tests/test_client_sqlite_repository.py`).
- [x] Keep a single unified output contract and add legacy format adapters at ingestion boundaries.
  - [x] Added adapter module: `ela_pipeline/adapters/legacy_contract.py`.
  - [x] Added unified conversion entrypoint: `adapt_legacy_contract_doc(...)`.
  - [x] Adapter coverage:
    - [x] `linguistic_notes -> notes[]` mapping (`source=legacy`)
    - [x] CEFR aliases (`sentence_cefr|phrase_cefr|word_cefr -> cefr_level`)
    - [x] `"null" -> null` TAM normalization
    - [x] missing `linguistic_elements` normalization
  - [x] Added tests: `tests/test_legacy_contract_adapter.py`.
- [ ] Integrate legacy visualizer and editor features into the new app flow (without model duplication).
  - [x] Added bridge module: `ela_pipeline/legacy_bridge/visualizer_editor.py`.
  - [x] Added visualizer payload builders:
    - [x] `build_visualizer_payload(...)`
    - [x] `build_visualizer_payload_for_document(...)`
  - [x] Added editor patch helper: `apply_node_edit(...)` by `sentence_text + node_id + field_path`.
  - [x] Added framework-agnostic JSON bridge CLI: `ela_pipeline/runtime/client_api.py`.
  - [x] Added route-ready CLI commands for screen wiring:
    - [x] `visualizer-payload`
    - [x] `apply-edit`
  - [x] Render and bind these commands in concrete frontend screens/routes.
    - [x] Route shell created: `Projects -> Files -> Analyze -> Vocabulary -> Visualizer`.
    - [x] Visualizer screen renders tree payload structure (React recursive tree).
    - [x] Frontend API contract layer added for `ui-state`, `submit-media`, `backend-jobs`, `visualizer-payload`.
    - [x] Minimal editor interaction wired via `apply-edit`-compatible API method (`applyEdit`), with in-UI re-render after patch.
    - [x] Quick Node Edit touch-first UX refined:
      - [x] collapsed by default; explicit expand/collapse control
      - [x] node selection bound to node label tap/click (no manual node id input)
      - [x] Basic mode edits only contract-facing fields (`content`, `cefr_level`, `tense`, `linguistic_notes`, `translation`, `phonetic`)
      - [x] Advanced mode edits only linguist-facing curated fields (internal/system-only fields hidden)
      - [x] advanced value picker shows first 4 rows by default with conditional `Expand/Collapse Values` for overflow
      - [x] selected advanced value shown as dedicated value box near overflow toggle
    - [x] Visualizer sentence navigation bound to `Prev/Next` controls per loaded payload.
  - [ ] Replace current mock API transport with production transport wired to runtime/backend endpoints.
- [x] Add explicit license-gated runtime switch for phonetics by deployment mode (offline/distributed/backend).
  - [x] Added deployment mode resolution: `ELA_DEPLOYMENT_MODE` + CLI `--deployment-mode`.
  - [x] Added phonetic policy switch: `ELA_PHONETIC_POLICY=enabled|disabled|backend_only`.
  - [x] Integrated with runtime capability gate (`ela_pipeline/runtime/capabilities.py`) and inference CLI checks.
  - [x] Added/updated tests in `tests/test_runtime_capabilities.py`.
- [x] Update docs with end-user limitations in offline mode (phonetics unavailability and large-media delegation).
  - [x] `docs/ela_pipeline_full_documentation.md`
  - [x] `docs/next_stage_product_spec_2026-02-17.md`
  - [x] `docs/deploy_docker.md`
