# Prompt: Expand ELA Grammar Dataset to 10,000 Training Pairs

## Your Role

You are a computational linguistics expert and curriculum designer helping build a high-quality training dataset for a T5 seq2seq model. The model's task is: given a structural description of a grammatical construction in an English sentence, generate a concise, accurate **linguistic teaching note** explaining what that construction is and how it works.

---

## Project Background

We are building a dataset of **input → target** pairs where:

- **Input** = a structural JSON payload describing a grammatical construction (sentence, phrase, or word) extracted from a real English sentence via spaCy dependency parsing
- **Target** = a 1–4 sentence linguistic note, written in the style of a grammar reference book (Cambridge Grammar Today, Collins COBUILD, Farlex Grammar Rules, etc.)

The model has three **node types**, each with its own input format:

### Node type: Sentence
The input encodes the full sentence's grammatical structure (TAM = Tense-Aspect-Mood).
The target is a note explaining the grammatical construction of the whole sentence.

**Example:**
```
sentence: Let's forget it, shall we?
input payload fields:
  node_type: Sentence
  tam_construction: "present simple active modal=shall affirmative"
  tense: present
  aspect: simple
  voice: active
  mood: null

target: "Question tags can also be used to show your reaction to something that
someone has just said or implied, for example to show interest, surprise, or anger.
If you are telling someone to do something and you want to make your order sound
less forceful, you can do so by adding a question tag."
```

### Node type: Phrase
The input names a specific multi-word phrase extracted from the sentence.
The target explains what type of phrase it is and how it functions.

**Example:**
```
sentence: About 60 per cent of our students are women.
content: "About 60 per cent of our students"
topic: noun_phrase

target: "You can use percentages on their own as noun phrases when it is clear
what they refer to. Fractions are often given in a special form as a number of hundredths."
```

### Node type: Word
The input is a single word (lemma). The target is a brief lexical or grammatical note.

**Example:**
```
content: "carefully"
part_of_speech: ADV
topic: ADV

target: "Manner adverbials answer the question 'How?' and describe the way in
which an action is performed. Most manner adverbials are adverbs derived from
adjectives, typically ending in -ly."
```

---

## Current Dataset State

| Metric | Value |
|--------|-------|
| Total rows | 1,139 |
| Train / Dev / Test | 917 / 110 / 112 |
| Node type: Sentence | 148 (13%) |
| Node type: Phrase | 154 (14%) |
| Node type: Word | 837 (73%) |
| Grammar sources | 7 books |

**Covered grammar topics** (with approximate row counts in train):
- prepositional_phrases: 45
- adverb_phrase: 30
- conditional_sentences: 29
- perfect aspect: 22
- noun_phrase: 18
- progressive aspect: 16
- verb_phrase: 15
- passive_voice: 14
- adjective_phrase: 13
- relative_clauses: 10
- question_tags: 8
- existential constructions: 8
- participle_phrase: 7
- that_clause: 4
- reported_speech: 3
- adverbial_clause: 2
- comparative_phrase: 6
- Word-level entries (ADV, NOUN, ADJ, NUM, PRON, VERB): ~690 (mostly Simple English Wiktionary, very short definitions)

**Critical gap**: ~60% of Word rows come from Simple English Wiktionary with very short, low-information targets like `"toward the back end of a ship."` These give the model almost no grammatical signal.

---

## Current Quality Rules (Guards)

These rules are applied during dataset construction and QC. Please review them, identify weaknesses, and propose improvements.

### 1. Sentence Guards
- Must start with a capital letter
- Must not contain mid-sentence parenthetical ` ) ` (OCR artifacts)
- Must not contain ellipsis `…` or `...`
- Must not be a dialogue fragment (`Person A:`)
- Must not have unclosed parenthesis
- Must have a grammatical subject (spaCy `nsubj`/`nsubjpass`/`expl`)

### 2. Target (Note) Guards
- Must be ≥ 5 words
- Must end with terminal punctuation `.!?`
- Must contain at least one linguistic meta-term (passive, clause, tense, aspect, gerund, infinitive, modal, subject, object, etc.) — **this rule applies to Sentence rows only**

### 3. Conditional Sentences (topic-specific)
- Third conditional: if-clause must contain past perfect (`had + PP` or `'d + PP`); result clause must contain modal perfect (`would/could/might have`)
- Wish/if-only constructions must NOT be paired with third conditional notes
- Conditional result-only fragments (no `if`/`unless`) are dropped

### 4. Passive Voice
- If target claims a specific passive tense (present continuous passive, future passive, etc.), the sentence must actually contain that passive pattern
- `by`-agent notes require the word `by` in the sentence

### 5. Reported Speech
- Reported question note → content must contain a wh-word or `whether`
- Reported statement note → content must NOT start with a wh-question word

### 6. Comparative
- Irregular comparative note → content must not be a `more/less` periphrastic construction
- Equal comparison (`as...as`) note → content must not start with `more/less`
- `-er` form note → content must not be `more/less`

### 7. Imperative
- First-person imperative note → content must start with `let's`/`let me`/`let us`
- Negative imperative note → content should start with `don't`/`do not`

### 8. Adverb Position
- Mid-position adverb note → the adverb must actually be in mid-position in the sentence
  (heuristic: word position ratio ≤ 50% of sentence length; not immediately followed by subordinating conjunction)

### 9. Phrase Content Span
- Phrase/Word content must appear as a substring of `sentence_text`
- Comma-space normalization is applied (`" , "` → `", "`) before checking

### 10. Verb Phrase Shape
- "Simple verb phrase" note must not be paired with a multi-word (complex) VP content

### 11. OCR / Structural Drops
- Targets beginning with `(owever` or `(ere` (OCR-corrupted "However"/"Here") are dropped
- Phrase content shorter than 2 characters is dropped
- Isolated VP fragments labelled as Sentence are auto-fixed to Phrase

---

## Your Tasks

### Task 1: Audit and Improve the Quality Rules

Review the 11 rule groups above. For each:
- Identify any **loopholes** (constructions that should be caught but slip through)
- Identify any **over-strictness** (valid pairs that might be wrongly dropped)
- Propose **new rules** for grammar areas not yet covered

Specifically, please propose rules for these gap areas:
- Infinitive constructions (to + verb) — distinguishing bare infinitive vs. to-infinitive
- Gerund vs. present participle distinction
- Modal verbs (distinguishing epistemic vs. deontic modality)
- Subject-verb agreement errors used as examples
- Cleft sentences (It is... that..., What... is...)
- Inversion constructions (Never have I..., Only then did...)
- Emphatic do (I DO want...)
- Fronting / Topicalization
- Articles and determiners (a/an vs. the vs. zero article)
- Quantifiers (some/any/much/many/few/little/a lot of)
- Phrasal verbs (separable vs. inseparable)

### Task 2: English Grammar Coverage Map

Create a comprehensive, structured list of all major English grammar topics that should be covered in the dataset. For each topic, specify:
- **Topic key** (snake_case, e.g. `modal_verbs`)
- **Subtopics** (e.g. for `modal_verbs`: epistemic, deontic, dynamic, ability, permission, obligation, deduction)
- **Minimum rows needed** to give the model meaningful signal (suggest 30–50 per subtopic for Sentence/Phrase, 10–20 for Word)
- **Example sentence** for each subtopic
- **Example linguistic note** (target) for each subtopic

The coverage map should be structured so that when all topics are covered at the minimum row count, the total is approximately 10,000 rows, distributed as:
- ~20% Sentence rows
- ~30% Phrase rows
- ~50% Word rows (but these should come from grammar reference books, NOT simple dictionary definitions)

### Task 3: Generate New Training Pairs

Using the format below, generate **200 new high-quality training pairs** covering the most underrepresented topics. Prioritise:
1. Modal verbs (can/could/may/might/shall/should/will/would/must/ought to)
2. Infinitive constructions
3. Gerund and participle
4. Articles and determiners
5. Quantifiers
6. Cleft and inversion sentences
7. Phrasal verbs
8. Conjunctions and discourse markers

**Output format for each pair** (one JSON object per line):
```json
{
  "node_type": "Phrase",
  "topic_key": "modal_verbs",
  "subtopic": "epistemic_possibility",
  "sentence_text": "She might have left already.",
  "content": "might have left",
  "target": "The modal verb 'might have' is used to express epistemic possibility about a past event — the speaker is uncertain whether the action occurred. It combines the modal 'might' (possibility) with the perfect infinitive 'have + past participle' to refer to the past.",
  "quality_flags": ["has_modal", "perfect_infinitive", "past_reference"]
}
```

For Sentence rows, include also:
```json
{
  "node_type": "Sentence",
  "topic_key": "cleft_sentences",
  "subtopic": "it_cleft",
  "sentence_text": "It was John who broke the window.",
  "tam_construction": "past simple active affirmative",
  "tense": "past",
  "aspect": "simple",
  "voice": "active",
  "target": "An it-cleft sentence uses the structure 'It + be + focused element + relative clause' to highlight or emphasise a particular part of the sentence. In 'It was John who broke the window', the cleft construction focuses attention on John as the agent, contrasting him with others who might have done the action.",
  "quality_flags": ["it_cleft", "has_relative_clause", "focus_construction"]
}
```

### Task 4: Quality Checklist for Generated Pairs

For every pair you generate, self-verify against these criteria:

**Content checks:**
- [ ] `content` string appears verbatim in `sentence_text` (for Phrase/Word)
- [ ] `sentence_text` is a grammatically correct, natural English sentence
- [ ] `sentence_text` starts with a capital letter and ends with `.`, `?`, or `!`
- [ ] `sentence_text` has a grammatical subject (not a bare VP fragment)
- [ ] For Sentence rows: `sentence_text` is a complete sentence, not a fragment

**Target (note) checks:**
- [ ] The note is 1–4 sentences long
- [ ] The note contains at least one grammatical meta-term (tense, clause, modal, infinitive, etc.)
- [ ] The note is accurate and would appear in a grammar reference book
- [ ] The note is specific to the construction in the example, not just a generic definition
- [ ] The note does NOT simply repeat words from the sentence
- [ ] The note ends with `.`

**Topic alignment checks:**
- [ ] `topic_key` matches what the note actually teaches
- [ ] If the note claims a specific tense/construction, the sentence actually contains it
- [ ] If the note claims "passive", the sentence contains a `be + past participle` construction
- [ ] If the note claims "third conditional", the sentence has past perfect if-clause + modal perfect result

---

## Style Guide for Targets

Targets should be written in the authoritative, descriptive style of a grammar reference book. Examples of the target register:

**Good:**
> "The present perfect is used to talk about past events or states that are relevant to the present moment. It is formed with have/has + past participle. We often use it with time expressions such as already, yet, just, ever, and never."

**Bad (too vague):**
> "This is a grammar structure used in English."

**Bad (too technical/jargon-heavy):**
> "This construction exhibits the [+PERFECT] aspectual feature of the auxiliary HAVE in combination with the en-participle, denoting anterior temporal reference."

**Bad (repeats the example):**
> "In the sentence 'She might have left already', might have left is used."

The register should be accessible to an intermediate-level English learner (B1–B2 CEFR), similar to the style of "English Grammar in Use" by Raymond Murphy or "Collins COBUILD English Grammar".

---

## Constraints and Anti-patterns to Avoid

1. **No OCR artifacts** in targets: no `(owever`, `(ere`, `H.`, corrupted parentheses
2. **No dialogue fragments** as sentences: `Person A: Hello.` → invalid
3. **No sentences starting with lowercase**
4. **No ellipsis** (`...` or `…`) in sentence_text
5. **No mid-sentence parentheticals** like `She went ( I think ) to the shop`
6. **No truncated relative clauses**: `the man who was...` (sentence ends mid-RC)
7. **No periphrastic comparatives** paired with `-er` or irregular comparative notes
8. **No wish/if-only** sentences paired with third conditional notes
9. **No isolated VP fragments** as Sentence rows: `Have been waiting` (no subject) → invalid Sentence
10. **No Wiktionary-style one-line definitions** for grammar Word rows: the target must teach grammar, not just define the word

---

Produce your response in three clearly labeled sections:
1. **Improved Quality Rules** (Task 1)
2. **Grammar Coverage Map** (Task 2) — structured table
3. **200 New Training Pairs** (Task 3) — JSON, one object per line
