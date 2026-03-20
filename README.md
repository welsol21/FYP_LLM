# ELA — English Language Assistant

**Final Year Project · Vladyslav Rastvorov · MTU**

ELA helps language learners engage with authentic materials (audio, video, text) without simplification. It transcribes, analyses, and annotates content using a hybrid NLP + local ML pipeline, producing structured learning artefacts that are displayed in an interactive UI with progressive disclosure.

---

## What It Does

1. User uploads a media file (audio, video, text, PDF) via the desktop or mobile app.
2. The backend transcribes audio (Whisper ASR), parses the transcript with spaCy, and enriches each word and phrase with grammar labels, CEFR difficulty level, phonetic transcription (IPA), synonyms, and bilingual translation (M2M100, EN→RU).
3. The result is a validated **RLE (Recursive Linguistic Elements) JSON contract** — a `Sentence → Phrase → Word` tree where every node carries learning metadata.
4. The UI renders the contract as an expandable tree with bilingual subtitles, note panels, and a vocabulary export (CSV / JSON).

---

## Deliverables

| Deliverable | Description | Branch |
|---|---|---|
| **Desktop app** | Tauri v2 + React, Ubuntu 24.04, fully offline (ONNX models) | `tauri_app` |
| **Mobile PWA** | React + nginx Docker, Android Chrome, backend ML via server | `android_pwa_release_v2` |
| **NLP pipeline** | Python, spaCy, M2M100, Whisper, tabular CEFR classifier | `master` / `dev` |

---

## System Architecture

```
User media (mp3/mp4/txt/pdf)
        │
        ▼
┌─────────────────────────────────────────┐
│              ELA Backend                │
│  Whisper ASR → spaCy parse → Enrichment │
│  (CEFR · phonetics · synonyms · M2M100) │
│           → RLE JSON contract            │
│  SQLite (projects / files / analyses)   │
└──────────────┬──────────────────────────┘
               │
       ┌───────┴────────┐
       ▼                ▼
  Desktop app        PWA (Android)
  (Tauri v2)         (React + nginx)
  ONNX inference     Server-side ML
  fully offline      cloudflare tunnel
```

---

## Quick Start (Docker — PWA / server mode)

```bash
cp .env.example .env
docker compose up -d --build
```

Frontend: `http://localhost:8080`

The backend runs DB migrations on startup and loads ML models on first request.

**Required model files** (place in `artifacts/models/`):
- `m2m100_418M/pytorch_model.bin` — download via `python -m ela_pipeline.translate.prepare_m2m100`
- `whisper/` — downloaded automatically on first transcription

---

## Desktop App (Tauri, Ubuntu 24.04)

Install the `.deb` package:
```bash
sudo dpkg -i ela-desktop_0.15.14_amd64.deb
```

All ML models (Whisper, M2M100-ONNX, MMS-TTS) are bundled in the package. No internet connection required after install.

---

## Pipeline CLI

Run the full NLP pipeline on a text input:
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m ela_pipeline.inference.run \
  --text "She should have trusted her instincts before making the decision." \
  --translate --translation-provider m2m100 \
  --phonetic --cefr
```

See [docs/pipeline_cli.md](docs/pipeline_cli.md) for all options.

---

## RLE Contract

The core data structure is a recursive JSON tree:

```
Sentence
  ├── translation: "Ей следовало доверять своим инстинктам..."
  ├── phonetic: { uk: "...", us: "..." }
  └── linguistic_elements: [
        Phrase (verb group)
          └── Word: "trusted"
                ├── cefr_level: "B2"
                ├── part_of_speech: "VERB"
                ├── tense: "past"
                ├── phonetic: { uk: "trʌstɪd", us: "trʌstɪd" }
                └── synonyms: ["relied on", "believed in"]
      ]
```

Full schema reference: [docs/sample.json](docs/sample.json)

---

## Running Tests

```bash
source .venv/bin/activate
python -m unittest discover -s tests -v
```

---

## Documentation

| Doc | Purpose |
|---|---|
| [docs/pipeline_cli.md](docs/pipeline_cli.md) | Full CLI reference |
| [docs/deploy_docker.md](docs/deploy_docker.md) | Docker deployment |
| [docs/db_persistence.md](docs/db_persistence.md) | Database schema and migrations |
| [docs/ela_pipeline_full_documentation.md](docs/ela_pipeline_full_documentation.md) | Pipeline architecture deep-dive |
| [docs/licenses_inventory.md](docs/licenses_inventory.md) | Third-party model and library licences |
| [docs/sample.json](docs/sample.json) | Authoritative RLE contract example |
