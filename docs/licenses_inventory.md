# License Inventory (Tools, Models, Data)

Last updated: 2026-02-16  
Scope: runtime/training tooling used in this repository, selected model assets, and data-source policy docs.

## 1) Selected model policy

- Translation model (approved): `facebook/m2m100_418M`
  - License: `MIT`
  - Source: https://huggingface.co/facebook/m2m100_418M
  - Reason: multilingual coverage + commercial-friendly license.

## 2) Python/runtime tools used by project

Primary dependencies from `requirements.txt` and runtime code:

| Tool / Package | Used for | License type |
|---|---|---|
| `torch` | model training/inference backend | BSD-3-Clause |
| `transformers` | model loading/inference/training APIs | Apache-2.0 |
| `datasets` | dataset handling | Apache-2.0 |
| `evaluate` | evaluation helpers | Apache-2.0 |
| `accelerate` | training/inference acceleration | Apache-2.0 |
| `spacy` | parsing and linguistic analysis | MIT |
| `en-core-web-sm` | English spaCy model | MIT |
| `numpy` | numeric operations | BSD-3-Clause |
| `pandas` | data processing/reporting | BSD-3-Clause |
| `requests` | HTTP for ingestion scripts | Apache-2.0 |
| `rouge-score` | text-quality metric tooling | Apache-2.0 |
| `sentencepiece` | tokenizer backend (used by M2M100/T5 tokenizers) | Apache-2.0 |

Notes:
- `sentencepiece` and `rouge-score` metadata in local wheels can have empty `License` field; license type above is taken from upstream project/license declarations.
- Always re-check upstream license before major version upgrades.

## 3) Model assets used by current pipeline

| Model family | In-project usage | License type |
|---|---|---|
| `t5-small` (base for local fine-tuned note models) | note generation experiments/pipeline models | Apache-2.0 |
| `facebook/m2m100_418M` | multilingual translation stage (EN->RU first) | MIT |

## 4) Data-source licensing (corpus/reference layer)

Dataset/reference source licensing policy and allow/deny matrix are maintained in:
- `docs/grammar_reference_sources_2026-02-13.md`

This includes tracked licenses for UD/OANC/Tatoeba/Wikinews and ingestion provenance requirements.

## 5) Operational guardrails

- No model/tool is added to production path without explicit license entry in this file.
- Non-commercial licenses (for example, `CC-BY-NC-*`) are blocked for commercial deployment path.
- For every new dependency/model:
  1. add license type,
  2. add source URL,
  3. note usage context in this repository.

## 6) GPL Components Policy (phonetics track)

Planned phonetic stack candidates discussed for UK/US transcription:
- `espeak-ng` (GPL-3.0-or-later)
- `phonemizer` (GPL-3.0)

Commercial deployment policy for GPL components in this project:
- Allowed by default: backend-only/SaaS execution where users receive only API/JSON results.
- Legal review required before release: any customer-distributed artifacts (on-prem package, Docker image, desktop bundle, embedded appliance).
- Mandatory before enabling a GPL-backed feature in production:
  1. record component/version/license/source here,
  2. mark deployment mode (`backend-only` vs `distributed`) in release notes,
  3. pass legal/compliance gate for distributed deployments.

Implementation note:
- Output data (for example, phonetic strings inside our JSON contract) is treated as service output.
- This does not replace legal advice; enterprise/on-prem release must include formal legal review.
