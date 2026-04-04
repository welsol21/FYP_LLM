export function AboutPage() {
  return (
    <div className="about-page">
      <section className="about-hero">
        <h2 className="about-product-name">ELA</h2>
        <p className="about-tagline">English Language Assistant</p>
        <p className="about-lead">
          A tool that helps non-native English speakers understand authentic content —
          lectures, articles, videos, podcasts — without dumbing it down.
        </p>
      </section>

      <section className="about-section">
        <h3 className="about-section-title">What it does</h3>
        <p className="about-body">
          Submit a text, audio file, or video. ELA transcribes the speech (if needed),
          parses every sentence into a structured hierarchy of phrases and words,
          and enriches each element with grammar labels, CEFR difficulty levels,
          EN→RU translations, and IPA phonetics.
        </p>
        <p className="about-body">
          The result is an interactive tree you can explore — click a phrase to see
          its grammar role, tense, difficulty, and a plain-language explanation
          of why it works the way it does. No simplification. No paraphrasing.
          The original language stays intact.
        </p>
      </section>

      <section className="about-section">
        <h3 className="about-section-title">How it works</h3>
        <ul className="about-list">
          <li><strong>Parsing</strong> — spaCy dependency parser builds a Sentence → Phrase → Word tree deterministically.</li>
          <li><strong>Grammar enrichment</strong> — rule-based tense, aspect, mood, and voice detection; no LLM guesswork.</li>
          <li><strong>Linguistic notes</strong> — a fine-tuned T5 model generates concise pedagogical explanations per node, with template fallback.</li>
          <li><strong>Translation</strong> — local M2M100 model (418M parameters) translates every element; external providers (Lara, DeepL) as fallback.</li>
          <li><strong>Speech recognition</strong> — OpenAI Whisper, runs locally.</li>
          <li><strong>Structured output</strong> — every analysis is a validated JSON contract (the RLE schema) that is the same every time for the same input.</li>
        </ul>
      </section>

      <section className="about-section">
        <h3 className="about-section-title">Current state</h3>
        <p className="about-body">
          Live working product at{' '}
          <a className="about-link" href="https://el-a.uk" target="_blank" rel="noreferrer">
            el-a.uk
          </a>
          . Processes text, audio, and video. Bilingual subtitle generation.
          PWA — installable, works on mobile. All ML inference runs on the server,
          nothing sent to third-party AI APIs by default.
        </p>
      </section>

      <section className="about-section">
        <h3 className="about-section-title">Using this app</h3>
        <ol className="about-steps">
          <li>
            <strong>Media</strong> — upload audio or video. ELA transcribes it, analyses every
            sentence, and generates a bilingual subtitle video.
          </li>
          <li>
            <strong>Analyze</strong> — paste any English text for instant analysis. No audio needed.
          </li>
          <li>
            <strong>Vocabulary</strong> — review all words and phrases from your analyses, sorted by CEFR level.
          </li>
          <li>
            <strong>Visualizer</strong> — tap any node in the tree to see grammar role, tense,
            CEFR level, translation, phonetics, and explanation.
            The coloured underline shows which phrase is selected.
          </li>
          <li>
            <strong>Config</strong> — choose your translation provider and enter API keys.
            Default translation runs locally (M2M100), no external API required.
          </li>
        </ol>
      </section>

      <hr className="about-divider" />

      <section className="about-section about-investor">
        <h3 className="about-section-title about-investor-title">For Investors</h3>

        <div className="about-investor-block">
          <h4 className="about-investor-subtitle">The problem worth solving</h4>
          <p className="about-body">
            1.5 billion people are learning English right now. The overwhelming majority hit a ceiling
            when they move from classroom materials to real-world content — a TED talk, a technical article,
            a business podcast. The gap is not vocabulary. It is structure: learners don't have a map
            of how real sentences are built.
          </p>
          <p className="about-body">
            Existing tools either simplify the content (and defeat the purpose) or hand back a generic
            GPT explanation that is inconsistent, unchecked, and different every time.
          </p>
        </div>

        <div className="about-investor-block">
          <h4 className="about-investor-subtitle">The technical moat</h4>
          <p className="about-body">
            ELA's core output is the <strong>RLE contract</strong> — a validated, schema-enforced JSON
            structure that maps every sentence to its grammatical skeleton. This contract is:
          </p>
          <ul className="about-list">
            <li><strong>Deterministic</strong> — same input always produces the same structure.</li>
            <li><strong>Auditable</strong> — every label, note, and CEFR tag has a traceable source.</li>
            <li><strong>Cheap to produce</strong> — a domain-specific T5 model replaces dozens of GPT-4 calls per document. Cost per analysis is a fraction of a cent.</li>
            <li><strong>API-ready</strong> — each pipeline stage (parser, enrichment, CEFR tagger, subtitle aligner) is an independent service with a clean HTTP interface.</li>
          </ul>
        </div>

        <div className="about-investor-block">
          <h4 className="about-investor-subtitle">Revenue model</h4>
          <ul className="about-list">
            <li><strong>B2C subscriptions</strong> — individual learners, IELTS/TOEFL candidates, professionals. €10–15/month.</li>
            <li><strong>B2B institutional licensing</strong> — language schools and universities that need CEFR tagging, vocabulary extraction, and annotated materials at scale.</li>
            <li><strong>API microservices</strong> — EdTech platforms that want to add structured linguistic analysis without building NLP infrastructure. Usage-based billing, €99–499/month tiers.</li>
          </ul>
          <p className="about-body">
            The microservice model is the highest-margin path: it requires no additional headcount to scale
            and turns ELA's pipeline into infrastructure rather than a consumer product.
          </p>
        </div>

        <div className="about-investor-block">
          <h4 className="about-investor-subtitle">Why now</h4>
          <p className="about-body">
            The EdTech market passed $250B and is accelerating. At the same time, LLM fatigue is setting in —
            enterprise buyers increasingly want outputs that are consistent, explainable, and auditable,
            not a different answer every time. ELA's deterministic pipeline is positioned precisely at
            that intersection.
          </p>
          <p className="about-body">
            The core technology is built and working. What comes next is packaging, distribution,
            and the first institutional partnerships.
          </p>
        </div>

        <div className="about-investor-block">
          <h4 className="about-investor-subtitle">Get in touch</h4>
          <p className="about-body">
            Built by Vladyslav Rastvorov, MTU Cork, BSc Software Development (Final Year Project, 2025–2026).
            Supervised by Dr. Alex Vakaloudis and Prof. Nasir Ahmad.
          </p>
          <p className="about-body">
            <a className="about-link" href="mailto:r00274535@mymtu.ie">r00274535@mymtu.ie</a>
          </p>
        </div>
      </section>
    </div>
  )
}
