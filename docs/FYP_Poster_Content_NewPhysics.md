# FYP Academic Poster — Content Reference
## As implemented in `FYP_Poster_NewPhysics.html`
### ELA: English Language Assistant — Vladyslav Rastvorov, R00274535

---

## MTU Formatting Compliance

| Requirement | Status | Implementation |
|---|---|---|
| A1 Portrait (59×84cm) | ✅ | `@page { size: A1 portrait; margin: 10mm }` |
| White background | ✅ | All columns `#ffffff` |
| Calibri font | ✅ | `font-family: Calibri, 'Gill Sans', Arial` |
| Title Case headings (no ALL CAPS) | ✅ | `text-transform: none` everywhere |
| MTU logo top-left | ✅ | CSS-rendered crest + "MTU" wordmark (replace with official file before print) |
| Max 5 references, IEEE | ✅ | 5 references in footer |
| Readable at 1.5m | ✅ | Font sizes calibrated: screen×2.73 = A1 print |

**Font sizes at A1 print (screen pt × 2.73 scale factor):**

| Element | Screen | A1 Print | MTU Requires |
|---|---|---|---|
| Title | 20pt | ~55pt | 54pt |
| Author/Affiliations | 14.5pt | ~40pt | 40pt |
| Sub Headings | 13.2pt | ~36pt | 36pt |
| Body Text | 11pt | ~30pt | 30–32pt |
| Fine Print | 8.8pt | ~24pt | 24pt |

---

## Layout

**3-column grid, portrait A1.**

```
┌─────────────────────────────────────────────────────────────┐
│  [MTU logo]  Title · Subtitle · Author · Supervisors  [QR]  │  ← Navy header
├───────────────┬─────────────────┬───────────────────────────┤
│  LEFT         │  CENTRE         │  RIGHT                    │
│               │                 │                           │
│  Problem &    │  New Physics    │  Performance Metrics      │
│  Motivation   │  Principle      │  (3 metric boxes)         │
│               │                 │                           │
│  RLE Data     │  Duality Loop   │  Annotation Comparison    │
│  Model        │  Diagram        │                           │
│               │                 │  System Validation        │
│  Analysis     │  Key Insight:   │                           │
│  Pipeline     │  Placeholders   │  Conclusions              │
│  + PWA note   │                 │                           │
│               │  Agentic AI     │  Future Directions        │
│  Research     │  Implication    │                           │
│  Journey:     │                 │  [Live Demo QR]           │
│  What We      │  Training Data  │  www.el-a.uk              │
│  Tried        │  & Corpus Scale │                           │
├───────────────┴─────────────────┴───────────────────────────┤
│  References (IEEE, 5 max)   │   Acknowledgements            │  ← Navy footer
└─────────────────────────────────────────────────────────────┘
```

**Colour palette:**
- Header/Footer background: `#1B2A4A` (navy)
- Left column accent: `#2C4A8C` (blue)
- Centre column accent: `#8B1A1A` (deep red)
- Right column accent: `#1A5C2E` (forest green)
- Highlight: `#F5C518` (amber)
- All column/card backgrounds: `#ffffff`

---

## Header

- **MTU logo** — top-left. Currently CSS-rendered (4-quadrant coloured squares + "MTU" wordmark). **Replace with official MTU file from Canvas before printing.**
- **Title (20pt screen / ~55pt A1):** `ELA: English Language Assistant`
- **Subtitle (italic, amber):** `An AI-Assisted Framework for Authentic English Comprehension Using Recursive Linguistic Annotation`
- **Author line (14.5pt screen / ~40pt A1):** Vladyslav Rastvorov (R00274535) · BSc Honours in Computer Systems · Supervisor Semester 1 (Research Phase): Dr. Alex Vakaloudis · Supervisor Semester 2 (Implementation Phase): Dr. Nasir Ahmad · Department of Computer Science · MTU Cork · May 2025
- **GitHub QR code** — top-right, white box with amber border. Encodes `https://github.com/welsol21/FYP_LLM`. Label: `github.com/welsol21/FYP_LLM`.

---

## Left Column

### 1. Problem & Motivation
- Language platforms use pre-simplified materials; authentic English is inaccessible without structural guidance.
- Hypothesis: NLP + lightweight AI can *explain* authentic input without altering it.
- Three research questions (bullet list).

### 2. The RLE Data Model
- Core innovation: nested JSON hierarchy Sentence → Phrase → Word.
- Monospace tree showing all fields: translation, CEFR, POS, IPA, TAM, note.
- Language-agnostic schema; current focus: English → Russian.

### 3. Analysis Pipeline
- 8-step colour-coded vertical flow:
  ① Input → ② Whisper ASR → ③ spaCy 3.7 → ④ TAM Rules Engine → ⑤ Phrase Builder → ⑥ ML Layer (CEFR + T5 Notes) → ⑦ Contract Validator (v1/v2_strict) → ⑧ RLE JSON → Visualizer/Export
- Note below: "Deployed as Progressive Web App (PWA) — Android-installable, fully client-side."

### 4. Research Journey: What We Tried
Four-row table showing iterative research. Rejected approaches shown with strikethrough red styling; winning approach in green:

| Component | Rejected | Rejected | Won |
|---|---|---|---|
| CEFR Classification | DeBERTa ~~(underperformed)~~ | BERT ~~(same issue)~~ | **XGBoost Tabular ✓ (78.3%)** |
| Note Generation | GPT-4o ~~(cost/cloud)~~ | T5 raw notation ~~(failed to generalise)~~ | **T5 + Placeholders ✓ (ROUGE-L 0.81)** |
| Speech Recognition | — | — | **Whisper ✓ (WER 8.2%)** |
| Translation | GPT-4o ~~(opt-in only)~~ | — | **M2M100 ✓ (local, offline)** |

---

## Centre Column

### 5. The New Physics of Context–Pattern Interaction
- Dark navy principle box (amber text):
  > *"In open systems, context forms patterns. In closed systems, patterns form context."*
- Sub-label: "Principle discovered empirically during T5 fine-tuning"

### 6. The Duality Loop Diagram
Two panels inside a gradient box (blue-left / amber-right), connected by a central circle labelled **T5**:

- **Left panel — Open System / Training Phase** (blue border, 🌊):
  - "External context flows in. Diverse RLE trees carve a stable internal pattern — the 'River Bed' of the encoder's weight space."
  - Button: `Context → Pattern`

- **Centre connector:** circular arrow, labels "Open →" / "→ Closed"

- **Right panel — Closed System / Inference Phase** (amber border, 🔭):
  - "Frozen weights act as a Lens. Novel, unseen input is refracted into structured output: CEFR level, TAM annotation, pedagogical note."
  - Button: `Pattern → Context`

- **ML Mapping table** below diagram (2 rows: Open/Training/RLE trees shape weights; Closed/Inference/Frozen weights interpret input).

### 7. The Key Insight: Placeholder-Driven Learning
- Monospace diff box showing the breakthrough:
  - ❌ Raw: `"She gave him a book" → [VP gave][NP him]`
  - ✅ Template: `[SUBJ][V-PAST][IOBJ][DET][NOUN] → [TAM: past-simple][VOICE: active]`
- Yellow insight box: "This is closed-system behaviour: the internal pattern imposes structure on any incoming context."

### 8. Implication for Agentic AI
- LLM agents = closed systems in open environments.
- Duality principle predicts where agents succeed (stable patterns) and fail (distribution shift).
- Yellow insight box: "Understanding training as pattern-carving and inference as pattern-imposing offers a new lens for agent reliability research."

### 9. Training Data & Corpus Scale
Horizontal bar chart (proportional widths) of four corpora:

| Corpus | Bar | Size | Coverage |
|---|---|---|---|
| OANC | `████████████████████` (100%) | 30M+ tokens | B2–C2 advanced |
| UD GUM | `███` (17%) | 5.2M tokens | B1–B2 genre-aware |
| Gutenberg | `█` (5%) | 1M+ tokens | C1–C2 rare tense patterns |
| MASC | `▏` (2%) | ~500k tokens | Validation/control |

Two summary boxes below: `27,000 raw → 685 unique after dedup` · `6 CEFR levels (A1→C2), full-ladder per grammar class`.

---

## Right Column

### 10. Performance Metrics
Three large metric callout boxes:
- 🔵 **78.3%** — CEFR Classification Accuracy (XGBoost ensemble, 3,000-sentence corpus)
- 🔴 **0.81** — Note Relevance ROUGE-L (fine-tuned T5, held-out RLE set)
- 🟢 **8.2%** — ASR Word Error Rate (Whisper base, clean speech)

### 11. Annotation Backend Comparison
4-row table: GPT-4o (High, $$$, ✗ offline) · Rules only (Medium, Free, ✓) · **T5 fine-tuned** (High, Free, ✓) · XGBoost CEFR (78.3%, Free, ✓). T5 row highlighted green.

### 12. System Validation
Four objectives verified:
- O1: spaCy + TAM → schema-valid RLE for all test sentences ✓
- O2: CEFR 78.3%; T5 ROUGE-L 0.81 ✓
- O3: Linguistic Visualizer renders full RLE tree; JSON/CSV export ✓
- O4: Android PWA fully client-side ✓

### 13. Conclusions
- Explainable AI annotation makes authentic English pedagogically accessible without simplification.
- RLE schema is a viable human-interpretable recursive model.
- Context–Pattern Duality generalises to any open→closed learning system.
- Placeholder-driven T5 is lexically invariant — generalises to novel vocabulary.

### 14. Future Directions
1. **Tauri 2 Desktop App** — native offline .deb/Windows package with bundled ML models
2. **Translation Quality Gates** — ChrF round-trip scorer, length-ratio guards, n-gram penalty, M2M100 review queue
3. **M2M100 LoRA Fine-Tuning** — domain-specific refinement on accepted EN→RU pairs
4. **Additional target languages** — pluggable translator backends
5. **Real-time streaming ASR** — Whisper streaming for live conversation practice

### 15. Live Demo (bottom of right column)
- Navy box with white QR code (110×110px, white padding wrapper for quiet zone).
- Encodes `https://www.el-a.uk`
- Label: **Live Demo** (amber) · **www.el-a.uk** (bold white) · "Try it in your browser" (muted)

---

## Footer (Navy band)

**Left — References (IEEE):**
1. Honnibal, M. & Montani, I. (2017). spaCy: Industrial-strength NLP.
2. Raffel, C. et al. (2020). Exploring the Limits of Transfer Learning with T5. *JMLR.*
3. Radford, A. et al. (2023). Robust Speech Recognition via Large-Scale Weak Supervision. *ICML.*
4. Chen, T. & Guestrin, C. (2016). XGBoost: A Scalable Tree Boosting System. *ACM KDD.*
5. Levy, M. (1997). *Computer-Assisted Language Learning.* Oxford University Press.

**Right — Acknowledgements:**
Prof. Nasir Ahmad (Implementation Supervisor) · Dr. Alex Vakaloudis (Research Supervisor) · Department of Computer Science, MTU Cork · Inspired by *Eleonora Rastvorova*.

---

## QR Codes Summary

| ID | URL | Size | Location | Background |
|---|---|---|---|---|
| `#qrcode` | `https://github.com/welsol21/FYP_LLM` | 72×72px | Header top-right | White box, amber border |
| `#qrcode-live` | `https://www.el-a.uk` | 110×110px | Bottom of right column | White padding inside navy box |

Both generated client-side by `qrcodejs` (CDN). Requires internet on first open.
Color scheme: dark `#1B2A4A`, light `#ffffff`, correction level M.

---

## Before Printing Checklist

- [ ] Replace CSS MTU logo with official MTU file from Canvas
- [ ] Verify `https://www.el-a.uk` is live and responding
- [ ] Print settings: **Fit to page** + **A1 Portrait** + **Background graphics: ON**
- [ ] Proof-read all text at 100% zoom in print preview
- [ ] Confirm both QR codes scan correctly on printed output

---
*Last updated: 2026-04-01. Source of truth: `docs/FYP_Poster_NewPhysics.html`*
