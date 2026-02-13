# Grammar Reference Sources (2026-02-13)

Authoritative sources used to derive deterministic note templates and quality constraints:

1. Cambridge Dictionary - Grammar (British Grammar)
   - https://dictionary.cambridge.org/grammar/british-grammar/
2. British Council - English Grammar
   - https://www.britishcouncil.org/english/grammar
3. Purdue OWL - Grammar
   - https://owl.purdue.edu/owl/general_writing/grammar/index.html
4. Merriam-Webster - Grammar & Usage
   - https://www.merriam-webster.com/grammar
5. Universal Dependencies - Dependency relation inventory
   - https://universaldependencies.org/u/dep/index.html

How they were used:
- POS role wording and function-first phrasing conventions.
- Clause/phrase functional framing (subject, object, modifier, complement).
- Dependency-role alignment and terminology normalization.
- Deterministic template design for sentence/phrase/word note targets.

Note:
- The pipeline stores paraphrased, normalized template language; it does not copy long verbatim passages from the references.

## Large-Scale Dataset Sources (Licensing Triage)

Target ingestion scale: ~3000 sentences / ~9000 phrases / ~18000 words.

### ALLOW (recommended now)

1. UD English EWT (annotated syntax; direct fit for POS/dep features)
   - https://universaldependencies.org/treebanks/en_ewt/index.html
   - License: CC BY-SA 4.0
   - Use: sentence/phrase/word examples with dependency labels and roles.

2. Open American National Corpus (OANC)
   - https://anc.org/data/oanc/
   - License/terms: project states unrestricted use/redistribution (including commercial use).
   - Use: large volume of clean English text for additional coverage.

3. Tatoeba (English subset)
   - https://en.wiki.tatoeba.org/articles/show/using-the-tatoeba-corpus
   - License: CC BY 2.0 FR for sentence text by default (plus attribution requirement); some items may be CC0.
   - Use: short learner-friendly sentence inventory; keep attribution pipeline.

4. Wikinews (selected language editions with explicit CC-BY terms)
   - https://en.wikinews.org/wiki/Wikinews:Citation_guidelines
   - License: CC BY (historically 2.5 for older content, 4.0 for newer content in some editions/time ranges).
   - Use: sentence extraction with strict provenance per article/date/license snapshot.

### CONDITIONAL (allowed with extra policy checks)

1. Project Gutenberg
   - https://www.gutenberg.org/policy/license
   - Terms: many texts are effectively reusable in US; jurisdiction and trademark/packaging rules apply.
   - Policy: ingest only items verified as safe for our redistribution context; strip PG branding/license wrappers from extracted text when needed.

2. Wikimedia projects (Wikipedia/Wiktionary/etc.)
   - https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use
   - Terms: predominantly CC BY-SA 4.0 (+ GFDL compatibility context).
   - Policy: acceptable with attribution + ShareAlike compliance tracked in dataset metadata.

### DENY (for current pipeline scope)

1. Sources with NC/ND restrictions for underlying text (for example UD treebanks with NC licenses when we need broad reuse).
2. Sources without clear machine-readable license provenance at item level.
3. Crawled web corpora without robust per-document rights filtering (high legal risk for redistribution).

## Operational Policy

- Every imported item must store: `source_name`, `source_url`, `license`, `attribution_required`, `collected_at`.
- Data without explicit license evidence is excluded by default.
- We store normalized derivative notes/templates, not long verbatim source passages.
