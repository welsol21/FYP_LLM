# Dataset Ingestion Plan (2026-02-13)

## Goal

Build a licensed, provenance-tracked corpus for training:
- 3000 sentence-level examples
- 9000 phrase-level examples
- 18000 word-level examples

All records must be deterministic, reproducible, and compatible with current template-id and hybrid template+RAG roadmap.

## Allowed Sources (Current)

1. UD English EWT (CC BY-SA 4.0)
2. OANC (unrestricted use per project terms)
3. Tatoeba English subset (CC BY 2.0/CC0 by item; attribution required where applicable)
4. Wikinews selected content (CC BY; versioned attribution tracking required)

## Target Source Quotas (Initial)

Sentence-level (3000 total):
- UD EWT: 1200
- OANC: 900
- Tatoeba: 600
- Wikinews: 300

Phrase-level (9000 total):
- Derived from parsed sentence set using deterministic extraction rules
- Minimum 3 phrase records per sentence on average

Word-level (18000 total):
- Derived from parsed sentence set using deterministic extraction rules
- Minimum 6 word records per sentence on average

## Data Contract for Ingested Records

Each ingested sentence record must include:
- `id`
- `text`
- `source_name`
- `source_url`
- `license`
- `attribution_required`
- `collected_at`

Derived phrase/word records must include:
- `parent_sentence_id`
- `content`
- `node_type` (`Phrase` or `Word`)
- `part_of_speech`
- `dep_label`
- `grammatical_role`
- TAM fields where applicable (`tense`, `aspect`, `mood`, `voice`, `finiteness`)
- provenance copied from parent sentence

## Extraction Rules (Deterministic)

1. Parse each sentence with one pinned spaCy model/version.
2. Build phrase candidates from dependency subtrees using current project rules.
3. Exclude one-token phrases and low-value chunks already disallowed in v2 contract.
4. Build word nodes from token stream with normalized POS/feature mapping.
5. Generate context key for each node for template lookup and RAG indexing.

## Quality Gates (Must Pass)

1. License coverage: 100% of records have non-empty `license` and `source_name`.
2. Parse success rate: >= 99% sentence parse success.
3. Duplicate ratio:
   - sentence text exact-duplicate <= 5%
   - normalized note-target duplicate ratios within project gate thresholds
4. Distribution:
   - no source contributes > 50% of sentence records
   - POS/dep/TAM coverage non-zero for all active template families
5. Hard filter compliance:
   - banned prefixes/noise tokens are absent from generated targets
   - rejected-candidate cleanup rules remain deterministic

## Implementation Sequence

1. Implement ingestion scripts for each source with unified JSONL output.
2. Merge and normalize source outputs into canonical corpus file.
3. Run parser extraction to sentence/phrase/word datasets.
4. Build template-id targets and enforce current quality filters.
5. Train on GPU only, then run regression inference QC.
6. Publish metrics report and update canonical docs.

## Deliverables

- `data/raw_sources/*.jsonl` (licensed sentence corpus with provenance)
- `data/processed_ingested/{train,dev,test}.jsonl`
- quality report JSON in `docs/`
- updated experiment report with before/after quality metrics
