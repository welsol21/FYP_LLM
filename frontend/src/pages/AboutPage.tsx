import { useState } from 'react'

type Section = 'how' | 'investors' | null
type HowSub = 'overview' | 'projects' | 'analysis' | 'visualizer' | 'export'

const HOW_TABS: { id: HowSub; label: string }[] = [
  { id: 'overview',   label: 'Overview'    },
  { id: 'projects',   label: 'Projects'    },
  { id: 'analysis',   label: 'Analysis'    },
  { id: 'visualizer', label: 'Visualizer'  },
  { id: 'export',     label: 'Vocab & Export' },
]

export function AboutPage() {
  const [open, setOpen] = useState<Section>(null)
  const [howSub, setHowSub] = useState<HowSub>('overview')

  const toggle = (s: Section) => setOpen((prev) => (prev === s ? null : s))

  return (
    <div className="about-page">
      <section className="about-hero">
        <h2 className="about-product-name">ELA</h2>
        <p className="about-product-full">English Language Assistant</p>
        <div className="about-get-card">
          <p className="about-get-label">Upload a video, audio, or text. You get:</p>
          <ol className="about-get-list">
            <li>
              <strong>Linguistic analysis</strong> of every sentence — grammar structure,
              CEFR difficulty, translation, and phonetics in an interactive tree view.
            </li>
            <li>
              <strong>Ready-made artifacts</strong> — an MP4 video with dual-language
              audio and subtitles (EN + RU), an MP3 with dual-language voiceover,
              and a vocabulary list extracted from the content.
            </li>
            <li>
              <strong>Export</strong> of words and phrases for independent study
              or integration with other tools (spaced-repetition apps, dictionaries, LMS platforms).
            </li>
          </ol>
        </div>
      </section>

      <div className="about-btn-row">
        <button
          className={`about-big-btn${open === 'how' ? ' active' : ''}`}
          onClick={() => toggle('how')}
        >
          How it works
        </button>
        <button
          className={`about-big-btn${open === 'investors' ? ' active' : ''}`}
          onClick={() => toggle('investors')}
        >
          For investors
        </button>
      </div>

      {open === 'how' && (
        <section className="about-panel">
          <div className="about-how-tabs">
            {HOW_TABS.map((t) => (
              <button
                key={t.id}
                className={`about-how-tab${howSub === t.id ? ' active' : ''}`}
                onClick={() => setHowSub(t.id)}
              >
                {t.label}
              </button>
            ))}
          </div>

          {howSub === 'overview' && (
            <div className="about-how-body">
              <p className="about-panel-intro">
                The interface is built for touch — every action is a single tap.
              </p>
              <div className="about-gesture-list">
                <div className="about-gesture">
                  <span className="about-gesture-icon">☰</span>
                  <div><strong>Bottom bar</strong> — tap <em>Media</em>, <em>Analyze</em>,
                  or <em>Vocabulary</em> to switch sections.</div>
                </div>
                <div className="about-gesture">
                  <span className="about-gesture-icon">⇐</span>
                  <div><strong>Back</strong> — top-left corner returns to the previous screen.</div>
                </div>
                <div className="about-gesture">
                  <span className="about-gesture-icon">⚙</span>
                  <div><strong>Config / About</strong> — top-right corner.
                  Set your translation provider and API keys in Config.</div>
                </div>
              </div>
            </div>
          )}

          {howSub === 'projects' && (
            <div className="about-how-body">
              <p className="about-panel-intro">
                All your work is organised into projects. Each project holds its own files and analyses.
              </p>
              <div className="about-gesture-list">
                <div className="about-gesture">
                  <span className="about-gesture-icon">＋</span>
                  <div><strong>Create a project</strong> — tap the <em>+</em> button on the
                  home screen. Give it a name and tap Save.</div>
                </div>
                <div className="about-gesture">
                  <span className="about-gesture-icon">↗</span>
                  <div><strong>Upload files</strong> — open a project, tap <em>Add file</em>.
                  Supported: MP4, MP3, WAV, PDF, DOCX, plain text. Files are stored locally in your browser.</div>
                </div>
                <div className="about-gesture">
                  <span className="about-gesture-icon">◉◉</span>
                  <div><strong>Open analysis</strong> — <strong>double-tap</strong> a file row
                  (two taps within 350 ms) to open it for analysis. A single tap only selects the row.</div>
                </div>
                <div className="about-gesture">
                  <span className="about-gesture-icon">✕</span>
                  <div><strong>Delete a file</strong> — tap the delete icon on the file card.
                  Confirm in the dialog — this also removes all related analyses and artifacts.</div>
                </div>
              </div>
            </div>
          )}

          {howSub === 'analysis' && (
            <div className="about-how-body">
              <p className="about-panel-intro">
                Analysis processes your file sentence by sentence and produces the full linguistic contract.
              </p>
              <div className="about-gesture-list">
                <div className="about-gesture">
                  <span className="about-gesture-icon">▶</span>
                  <div><strong>Start analysis</strong> — open a file and tap <em>Analyse</em>.
                  For audio/video, speech is transcribed first via Whisper, then each sentence is parsed.</div>
                </div>
                <div className="about-gesture">
                  <span className="about-gesture-icon">⟳</span>
                  <div><strong>Progress</strong> — a progress bar shows sentence-by-sentence processing.
                  You can leave the screen; analysis continues in the background.</div>
                </div>
                <div className="about-gesture">
                  <span className="about-gesture-icon">T</span>
                  <div><strong>Text input</strong> — tap <em>Analyze</em> in the bottom bar to
                  type or paste text directly, without uploading a file.</div>
                </div>
                <div className="about-gesture">
                  <span className="about-gesture-icon">🌐</span>
                  <div><strong>Translation</strong> — enabled by default using the local M2M100 model.
                  Switch provider in Config if you have a Lara or DeepL key.</div>
                </div>
                <div className="about-gesture">
                  <span className="about-gesture-icon">📄</span>
                  <div><strong>full_text.txt</strong> — plain text transcript of the entire file.
                  For audio/video this is the Whisper transcription; for documents it is the extracted text.</div>
                </div>
                <div className="about-gesture">
                  <span className="about-gesture-icon">📋</span>
                  <div><strong>media_contract.json</strong> — the full linguistic contract for the
                  entire document: every sentence, phrase, and word with all enrichment data.</div>
                </div>
                <div className="about-gesture">
                  <span className="about-gesture-icon">📋</span>
                  <div><strong>contract_sentences.json</strong> — the same contract split into
                  individual sentence records, easier to process programmatically.</div>
                </div>
                <div className="about-gesture">
                  <span className="about-gesture-icon">🎵</span>
                  <div><strong>translated_audio_ru.mp3</strong> — bilingual audio track:
                  each sentence spoken in English then in Russian (TTS).</div>
                </div>
                <div className="about-gesture">
                  <span className="about-gesture-icon">💬</span>
                  <div><strong>subtitles_bilingual.srt</strong> — subtitle file with both English
                  and Russian on each cue. Drop it into any video player or editor.</div>
                </div>
                <div className="about-gesture">
                  <span className="about-gesture-icon">💬</span>
                  <div><strong>subtitles_en.srt / subtitles_target.srt</strong> — English-only
                  and Russian-only subtitle files separately.</div>
                </div>
                <div className="about-gesture">
                  <span className="about-gesture-icon">🎬</span>
                  <div><strong>Rendered video (MP4)</strong> — the original video with bilingual
                  subtitles and dual-language voiceover burned in. Generated on demand via the
                  Render button on the results screen.</div>
                </div>
              </div>
            </div>
          )}

          {howSub === 'visualizer' && (
            <div className="about-how-body">
              <p className="about-panel-intro">
                The Visualizer shows the grammatical tree of a sentence. Tap anything to explore it.
              </p>
              <div className="about-gesture-list">
                <div className="about-gesture">
                  <span className="about-gesture-icon">↓</span>
                  <div><strong>Open</strong> — tap any sentence card in the results list
                  to open its Visualizer.</div>
                </div>
                <div className="about-gesture">
                  <span className="about-gesture-icon">◉</span>
                  <div><strong>Expand a node</strong> — tap a phrase or word node to open
                  its detail card: grammar role, tense, CEFR level, translation, phonetics,
                  and a plain-language explanation. Tap again to collapse.</div>
                </div>
                <div className="about-gesture">
                  <span className="about-gesture-icon">_</span>
                  <div><strong>Sentence highlight</strong> — a coloured underline on the sentence
                  at the top shifts as you tap nodes, showing exactly which words belong
                  to the selected phrase.</div>
                </div>
                <div className="about-gesture">
                  <span className="about-gesture-icon">✎</span>
                  <div><strong>Node Edit</strong> — tap this button in the toolbar to
                  manually edit the text or metadata of the currently selected node.</div>
                </div>
                <div className="about-gesture">
                  <span className="about-gesture-icon">📖</span>
                  <div><strong>Note Level</strong> — switches the linguistic explanation between
                  <em> Elementary</em>, <em>Intermediate</em>, <em>Advanced</em>, or <em>All</em> levels
                  so you see the explanation that fits your proficiency.</div>
                </div>
                <div className="about-gesture">
                  <span className="about-gesture-icon">🌐</span>
                  <div><strong>Translate</strong> — switches which provider's translation is
                  displayed on each node (M2M100, Lara, DeepL, or all at once).</div>
                </div>
                <div className="about-gesture">
                  <span className="about-gesture-icon">⇅</span>
                  <div><strong>Scroll</strong> — swipe up/down to navigate a long sentence tree.</div>
                </div>
              </div>
            </div>
          )}

          {howSub === 'export' && (
            <div className="about-how-body">
              <p className="about-panel-intro">
                The Vocabulary tab aggregates everything extracted across all your analyses.
                Select entries to export or open in the Visualizer.
              </p>
              <div className="about-gesture-list">
                <div className="about-gesture">
                  <span className="about-gesture-icon">☑</span>
                  <div><strong>Select entries</strong> — tap any row in the Vocabulary list to
                  select it. Tap again to deselect. The action bar appears when at least one
                  row is selected.</div>
                </div>
                <div className="about-gesture">
                  <span className="about-gesture-icon">◉</span>
                  <div><strong>Open in Visualizer</strong> — with rows selected, tap
                  <em> Visualizer</em> in the action bar to jump directly to the grammatical
                  tree for those sentences.</div>
                </div>
                <div className="about-gesture">
                  <span className="about-gesture-icon">⬇</span>
                  <div><strong>Export JSON / CSV</strong> — tap <em>Export JSON</em> or
                  <em> Export CSV</em> to download the selected vocabulary with all metadata.
                  Choose which fields to include before confirming.</div>
                </div>
                <div className="about-gesture">
                  <span className="about-gesture-icon">✕</span>
                  <div><strong>Delete analyses</strong> — select rows and tap
                  <em> Delete Analyses</em> to remove them and free up storage.</div>
                </div>
              </div>
            </div>
          )}
        </section>
      )}

      {open === 'investors' && (
        <section className="about-panel">
          <div className="about-investor-block">
            <h4 className="about-investor-subtitle">The problem</h4>
            <p className="about-body">
              1.5 billion people are learning English. Most hit a ceiling when they move from
              classroom materials to real content — lectures, podcasts, articles. Existing tools
              either simplify the content or return a different GPT answer every time.
            </p>
          </div>

          <div className="about-investor-block">
            <h4 className="about-investor-subtitle">The technical moat</h4>
            <p className="about-body">
              ELA produces a <strong>validated, schema-enforced JSON contract</strong> for every
              sentence — deterministic, auditable, same output every time. A domain-specific T5
              model replaces dozens of GPT-4 calls per document, cutting compute cost by an
              order of magnitude.
            </p>
          </div>

          <div className="about-investor-block">
            <h4 className="about-investor-subtitle">Revenue model</h4>
            <ul className="about-list">
              <li><strong>B2C</strong> — individual learners, €10–15/month subscription.</li>
              <li><strong>B2B</strong> — language schools and universities licensing CEFR tagging,
              vocabulary extraction, and annotation at scale.</li>
              <li><strong>API microservices</strong> — EdTech platforms integrating the pipeline
              as infrastructure. Usage-based billing, €99–499/month.</li>
            </ul>
          </div>

          <div className="about-investor-block">
            <h4 className="about-investor-subtitle">Current state</h4>
            <p className="about-body">
              Live working product at{' '}
              <a className="about-link" href="https://el-a.uk" target="_blank" rel="noreferrer">el-a.uk</a>.
              Processes text, audio, and video. All ML inference runs on the server —
              no dependency on third-party AI APIs. Built as Final Year Project, MTU Cork, 2025–2026.
            </p>
          </div>

          <div className="about-investor-block">
            <h4 className="about-investor-subtitle">Contact</h4>
            <p className="about-body">
              Vladyslav Rastvorov —{' '}
              <a className="about-link" href="mailto:r00274535@mymtu.ie">r00274535@mymtu.ie</a>
            </p>
          </div>

          <a
            className="about-pitch-btn"
            href="/investor-pitch.html"
            target="_blank"
            rel="noreferrer"
          >
            ↓ Full investor pitch (open &amp; save as PDF)
          </a>
        </section>
      )}
    </div>
  )
}
