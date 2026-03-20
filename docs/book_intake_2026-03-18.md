**Book Intake 2026-03-18**

This note records the current triage of the newly provided grammar books.

**Current Canonical Corpus Base**

- Current canonical working corpus: `data/processed_corpus_book_projection_v15/ingested_corpus_book_projection_v15.jsonl`
- `v15` is the continuation of `v14` after the combined `Mark Lester + Azar` ingestion wave.
- `v15` improved the sentence layer materially again:
  - `sentence_rows_with_notes`: `413 -> 1040`
  - `covered_rows`: `1845 -> 2201`
  - `rows_total`: `3473 -> 3505`
- The new wave was sentence-first by design, so the phrase layer stayed flat while sentence coverage expanded:
  - `phrase_rows_with_notes`: `1553 -> 1553`
  - `phrase_candidate_total`: `7223 -> 7223`
- Phrase inflation was intentionally blocked during merge (`phrase_mode=fill_empty_only`), so `v15` adds sentence value without flooding the phrase layer with generic repeats.

**Primary Note Sources**

- `Collins Cobuild English Grammar - 2011.epub`
  Clean machine-readable EPUB, corpus-based explanations, dense coverage of sentence and phrase grammar, and strong note potential for:
  `passive`, `questions`, `negation`, `modals`, `verb phrases`, `noun phrases`, `reporting verbs`, `relative clauses`.
  This source has now been ingested into the main workflow as the basis of `v14`.

- `Collins Cobuild English Grammar - 2011.pdf`
  Backup to the EPUB. Usable text extraction, but the EPUB is structurally easier to mine.

- `Mark Lester - English Grammar Drills - 2009.pdf`
  Promising selective source. It is exercise-heavy, but the mini-unit structure is dense and gives reusable explanations for:
  `relative clauses`, `noun clauses`, `passive`, `questions and negatives`, `noun phrases`, `verb phrases`.
  This source has now been ingested into the main workflow as part of `v15`.

**Secondary Note Sources**

- `Betty Scrampfer Azar - Basic English Grammar, Second Edition - 1996.pdf`
  Good clean text extraction and strong coverage of basic sentence patterns. More textbook-like and lower-level than COBUILD, so it should be mined selectively rather than broadly.
  This source has now been ingested selectively into the main workflow as part of `v15`.

**Word-Note / Dictionary Candidates**

- `West M., Kimber P. F. - Deskbook of Correct English ... 1963.djvu`
  Intended candidate for word-level notes and usage notes, but the current file appears corrupted under `djvutxt` and needs a better copy before intake.

- `George Yule - Explaining English Grammar - 1998.djvu`
  Strong candidate for sentence, phrase, and possibly word-level explanatory notes. DJVU extraction works and the table of contents shows usable chapters on:
  `articles`, `tense and aspect`, `modals`, `conditionals`, `prepositions and particles`, `indirect objects`, `infinitives and gerunds`, `relative clauses`, and `direct/indirect speech`.

**Tooling Status**

- `djvulibre-bin` is now installed in the environment.
- `George Yule - Explaining English Grammar - 1998.djvu` is extractable.
- `West ... Deskbook ... 1963.djvu` appears corrupted and cannot currently be mined automatically.
- `George Yule - Explaining English Grammar - 1998.djvu` has now been ingested into the main book-to-corpus workflow as the basis of `v13`.
- `Collins Cobuild English Grammar - 2011.epub` has now been ingested into the main book-to-corpus workflow as the basis of `v14`.
- `Mark Lester - English Grammar Drills - 2009.pdf` and `Betty Scrampfer Azar - Basic English Grammar, Second Edition - 1996.pdf` have now been ingested into the main book-to-corpus workflow as the basis of `v15`.

**Reject / Reference / Not Worth Pipeline Time**

- `Kenna Bourke - Test It Fix It Intermediate. English Grammar - 2003.pdf`
  Scanned workbook with unusable text extraction.

- `Kenna Bourke - Test It Fix It Pre-Intermediate. English Grammar - 2003.pdf`
  Same issue as the intermediate volume.

- `A.Wallwork - English for Research Usage, Style, and Grammar - 2013.pdf`
  Good style and academic writing guide, but not a strong source for transferable sentence/phrase grammar notes in our product format.

- `Азar Betty - Basic English Grammar Test bank (Second Edition) - 1999.pdf`
  Test bank, not note source.

- `Basic English Grammar KEY.pdf`
  Answer key, not note source.

- `Джозеф Райт- Баовая среднеанглийская грамматика(1923).djvu`
  Outside the scope of modern English learner-facing notes.

- `2- Can Improving Your English Skills Make You More Employable.pdf`
  Not a grammar source for the pipeline.

**Current Blocker**

There is no tooling blocker for DJVU anymore. The main bottleneck is now
source quality and curation density: we should prioritize books that add
strong sentence-level notes without flooding the corpus with repetitive
phrase-level paraphrases.

**Current Ingestion Priority**

1. word-note dictionary sources, if we obtain a non-corrupted copy of `West ... Deskbook ... 1963.djvu`
2. other extractable dictionaries or glossaries for word notes
3. any remaining high-density sentence-note books that add new sentence families rather than generic phrase paraphrases
