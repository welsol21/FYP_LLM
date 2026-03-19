**Goal**
Move note generation away from free-form T5 targets toward a classifier-first pipeline:

`compact structural prompt -> template_id classifier -> deterministic renderer with slots`

The enriched `v16` corpus shows that the current template registry is too coarse, especially on the sentence layer. The main bottleneck is not book ingestion anymore; it is insufficient template granularity.

**Current Evidence**
Source report:
[template_expansion_proposal_v16.json](/home/vlad/Dev/FYP_LLM/data/reports/template_expansion_proposal_v16.json)

Top sentence families extracted from the enriched corpus:
- `SENT_NEGATION_GENERAL`
- `SENT_NEGATION_DO_SUPPORT`
- `SENT_QUESTION_WH`
- `SENT_QUESTION_YES_NO_AUX`
- `SENT_QUESTION_YES_NO_DO_SUPPORT`
- `SENT_QUESTION_TAG`
- `SENT_EXISTENTIAL_THERE`
- `SENT_EXISTENTIAL_THERE_AGREEMENT`
- `SENT_NOUN_CLAUSE_THAT`
- `SENT_NOUN_CLAUSE_WH`
- `SENT_EXTRAPOSITION_IT_THAT`
- `SENT_PASSIVE_GENERAL`
- `SENT_CONDITIONAL_GENERAL`
- `SENT_CONDITIONAL_PRESENT_MODAL`
- `SENT_CONDITIONAL_FIRST`
- `SENT_CONDITIONAL_SECOND`
- `SENT_TIME_CLAUSE_FUTURE_REFERENCE`
- `SENT_CLEFT_IT`
- `SENT_IMPERATIVE`

Top phrase families extracted from the enriched corpus:
- `PHRASE_PP_GENERAL`
- `PHRASE_PP_LOCATION`
- `PHRASE_PP_TIME`
- `PHRASE_PP_SOURCE`
- `PHRASE_PP_PURPOSE`
- `PHRASE_PP_AGENT`
- `PHRASE_PP_MEANS`
- `PHRASE_PP_ASSOCIATION`
- `PHRASE_RELATIVE_CLAUSE`
- `PHRASE_RELATIVE_CLAUSE_RESTRICTIVE`
- `PHRASE_RELATIVE_CLAUSE_NONRESTRICTIVE`
- `PHRASE_RELATIVE_CLAUSE_STRANDED_PREP`
- `PHRASE_RELATIVE_CLAUSE_FRONTED_PREP`
- `PHRASE_VP_GENERAL`
- `PHRASE_VP_MODAL`
- `PHRASE_VP_PROGRESSIVE`
- `PHRASE_VP_PERFECT`
- `PHRASE_VP_PERFECT_PROGRESSIVE`
- `PHRASE_VP_PASSIVE`
- `PHRASE_VP_INFINITIVE`
- `PHRASE_VP_ING_NONFINITE`
- `PHRASE_VP_PHRASAL_VERB`
- `PHRASE_VP_COLLOCATION`

**Wave 1 Registry Expansion**
Add these sentence templates first:
- `SENT_NEGATION_GENERAL`
- `SENT_NEGATION_DO_SUPPORT`
- `SENT_QUESTION_WH`
- `SENT_QUESTION_YES_NO_AUX`
- `SENT_QUESTION_YES_NO_DO_SUPPORT`
- `SENT_QUESTION_TAG`
- `SENT_EXISTENTIAL_THERE`
- `SENT_EXISTENTIAL_THERE_AGREEMENT`
- `SENT_NOUN_CLAUSE_THAT`
- `SENT_NOUN_CLAUSE_WH`
- `SENT_EXTRAPOSITION_IT_THAT`
- `SENT_PASSIVE_GENERAL`
- `SENT_PASSIVE_AGENTLESS`
- `SENT_PASSIVE_PROGRESSIVE`
- `SENT_CONDITIONAL_GENERAL`
- `SENT_CONDITIONAL_PRESENT_MODAL`
- `SENT_CONDITIONAL_FIRST`
- `SENT_CONDITIONAL_SECOND`
- `SENT_TIME_CLAUSE_FUTURE_REFERENCE`
- `SENT_CLEFT_IT`
- `SENT_IMPERATIVE`

Add these phrase templates second:
- `PHRASE_PP_GENERAL`
- `PHRASE_PP_LOCATION`
- `PHRASE_PP_TIME`
- `PHRASE_PP_SOURCE`
- `PHRASE_PP_PURPOSE`
- `PHRASE_PP_AGENT`
- `PHRASE_PP_MEANS`
- `PHRASE_PP_ASSOCIATION`
- `PHRASE_RELATIVE_CLAUSE`
- `PHRASE_RELATIVE_CLAUSE_RESTRICTIVE`
- `PHRASE_RELATIVE_CLAUSE_NONRESTRICTIVE`
- `PHRASE_RELATIVE_CLAUSE_STRANDED_PREP`
- `PHRASE_RELATIVE_CLAUSE_FRONTED_PREP`
- `PHRASE_VP_GENERAL`
- `PHRASE_VP_MODAL`
- `PHRASE_VP_PROGRESSIVE`
- `PHRASE_VP_PERFECT`
- `PHRASE_VP_PERFECT_PROGRESSIVE`
- `PHRASE_VP_PASSIVE`
- `PHRASE_VP_INFINITIVE`
- `PHRASE_VP_ING_NONFINITE`
- `PHRASE_VP_PHRASAL_VERB`
- `PHRASE_VP_COLLOCATION`

**Model Recommendation**
For `template_id` prediction, prefer a classifier, not T5.

Recommended order:
1. `DeBERTa-v3-small`
2. `DeBERTa-v3-base`
3. plain `BERT` only if we need the simplest baseline

Why:
- template prediction is a closed-label classification task
- the current dataset is too small and too heterogeneous for stable free-form seq2seq generation
- classifiers are more data-efficient for low-entropy targets
- deterministic rendering gives us controllable outputs and easy validation

**Practical Architecture**
1. Build a compact prompt from the node and local tree context.
2. Predict `template_id` with a sequence classifier.
3. Validate semantic compatibility of `template_id` against the node contract.
4. Render the note deterministically from template text plus slots.
5. Keep T5 only as an optional later-stage paraphrase renderer, not as the core generator.

**Decision**
The next mainline experiment should be:

`v16 projected corpus -> template-expanded label set -> DeBERTa classifier -> deterministic template renderer`

not another free-form T5 note generator run.
