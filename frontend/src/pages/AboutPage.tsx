import { useState } from 'react'

type Section = 'how' | 'investors' | null

export function AboutPage() {
  const [open, setOpen] = useState<Section>(null)

  const toggle = (s: Section) => setOpen((prev) => (prev === s ? null : s))

  return (
    <div className="about-page">
      <section className="about-hero">
        <h2 className="about-product-name">ELA</h2>
        <p className="about-lead">
          Upload a video, audio, or text — get a full linguistic breakdown of every sentence:
          grammar structure, CEFR level, translation, and phonetics, all in one interactive view.
        </p>
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
          <p className="about-panel-intro">
            The interface is built for touch — every action is a single tap or a swipe.
          </p>

          <div className="about-gesture-list">
            <div className="about-gesture">
              <span className="about-gesture-icon">☰</span>
              <div>
                <strong>Bottom bar</strong> — tap <em>Media</em>, <em>Analyze</em>, or <em>Vocabulary</em>
                to switch between the main sections.
              </div>
            </div>

            <div className="about-gesture">
              <span className="about-gesture-icon">＋</span>
              <div>
                <strong>Start analysis</strong> — on the Media screen tap the upload area or the
                microphone button to add a file. On Analyze, type or paste text and tap <em>Analyse</em>.
              </div>
            </div>

            <div className="about-gesture">
              <span className="about-gesture-icon">↓</span>
              <div>
                <strong>Open a result</strong> — after analysis finishes, tap any sentence card
                in the list to open the Visualizer for that sentence.
              </div>
            </div>

            <div className="about-gesture">
              <span className="about-gesture-icon">◉</span>
              <div>
                <strong>Explore the tree</strong> — in the Visualizer, tap any phrase or word node
                to expand its detail card: grammar role, tense, CEFR level, translation, and phonetics.
                Tap again to collapse.
              </div>
            </div>

            <div className="about-gesture">
              <span className="about-gesture-icon">_</span>
              <div>
                <strong>Sentence highlight</strong> — as you tap nodes in the tree, the coloured
                underline on the sentence at the top shifts to show exactly which words belong
                to the selected phrase.
              </div>
            </div>

            <div className="about-gesture">
              <span className="about-gesture-icon">⇐</span>
              <div>
                <strong>Go back</strong> — tap <em>Back</em> in the top-left corner to return
                to the previous screen. Swipe right on mobile also works.
              </div>
            </div>

            <div className="about-gesture">
              <span className="about-gesture-icon">⚙</span>
              <div>
                <strong>Config</strong> — tap in the top-right corner to set your translation
                provider. Default translation runs locally — no account needed.
              </div>
            </div>
          </div>
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
        </section>
      )}
    </div>
  )
}
