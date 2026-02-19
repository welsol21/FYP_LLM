import { useEffect, useState } from 'react'
import { useApi } from '../api/apiContext'
import type { MediaSubmissionPayload, TranslationProviderConfig } from '../api/runtimeApi'

type Props = {
  onSubmitted: (payload: MediaSubmissionPayload) => void
  projectId: string | null
  projectLabel: string
  stageProgress: number[]
  initialMedia?: {
    mediaFileId?: string
    mediaPath?: string
    durationSec?: number
    sizeBytes?: number
    fileName?: string
  }
  translatorOptions: TranslationProviderConfig[]
  defaultTranslator: string
}

const STAGES = ['Loading file', 'Transcribing audio', 'Translating text', 'Generating media', 'Exporting files']

function hasRequiredCredentials(provider: TranslationProviderConfig): boolean {
  if (!provider.credential_fields.length) return true
  return provider.credential_fields.every((field) => String(provider.credentials[field] || '').trim().length > 0)
}

export function MediaSubmitForm({
  onSubmitted,
  projectId,
  projectLabel,
  stageProgress,
  initialMedia,
  translatorOptions,
  defaultTranslator,
}: Props) {
  const api = useApi()
  const [mediaPath, setMediaPath] = useState('')
  const [durationSec, setDurationSec] = useState(600)
  const [sizeBytes, setSizeBytes] = useState(100 * 1024 * 1024)
  const [mediaFileId, setMediaFileId] = useState<string | undefined>(undefined)
  const [selectedFileName, setSelectedFileName] = useState('')
  const [translator, setTranslator] = useState(defaultTranslator || 'm2m100')
  const [subtitles, setSubtitles] = useState('Bilingual')
  const [voice, setVoice] = useState('Male')
  const [submitting, setSubmitting] = useState(false)
  const enabledProviders = translatorOptions.filter((p) => p.enabled && hasRequiredCredentials(p))
  const subtitleOptions = ['Bilingual', 'Target only', 'Source only']
  const voiceOptions = ['Male', 'Female']

  useEffect(() => {
    if (!initialMedia) return
    if (initialMedia.mediaPath) setMediaPath(initialMedia.mediaPath)
    if (typeof initialMedia.durationSec === 'number') setDurationSec(initialMedia.durationSec)
    if (typeof initialMedia.sizeBytes === 'number') setSizeBytes(initialMedia.sizeBytes)
    setMediaFileId(initialMedia.mediaFileId)
    setSelectedFileName(initialMedia.fileName ?? '')
  }, [initialMedia])

  useEffect(() => {
    if (defaultTranslator) setTranslator(defaultTranslator)
  }, [defaultTranslator])

  useEffect(() => {
    if (!enabledProviders.length) return
    const hasCurrent = enabledProviders.some((p) => p.id === translator)
    if (!hasCurrent) setTranslator(enabledProviders[0].id)
  }, [enabledProviders, translator])

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setSubmitting(true)
    try {
      const payload = await api.submitMedia({
        mediaPath,
        durationSec,
        sizeBytes,
        projectId: projectId ?? undefined,
        mediaFileId,
        translationProvider: translator,
        subtitlesMode: subtitles.toLowerCase(),
        voiceChoice: voice.toLowerCase(),
      })
      onSubmitted(payload)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="analyze-panel" aria-label="media-submit-form">
      <div className="project-line">{projectLabel}</div>
      <div className="file-line">{selectedFileName || '-'}</div>

      <div className="analyze-grid">
        <label className="analyze-label">Translator:</label>
        <div className="touch-options-grid">
          {enabledProviders.map((p) => (
            <button
              key={p.id}
              type="button"
              className={`touch-option-btn${translator === p.id ? ' active' : ''}`}
              onClick={() => setTranslator(p.id)}
            >
              {p.label}
            </button>
          ))}
        </div>

        <label className="analyze-label">Subtitles:</label>
        <div className="touch-options-grid">
          {subtitleOptions.map((option) => (
            <button
              key={option}
              type="button"
              className={`touch-option-btn${subtitles === option ? ' active' : ''}`}
              onClick={() => setSubtitles(option)}
            >
              {option}
            </button>
          ))}
        </div>

        <label className="analyze-label">Voice:</label>
        <div className="touch-options-grid">
          {voiceOptions.map((option) => (
            <button
              key={option}
              type="button"
              className={`touch-option-btn${voice === option ? ' active' : ''}`}
              onClick={() => setVoice(option)}
            >
              {option}
            </button>
          ))}
        </div>
      </div>

      <div className="stage-list">
        {STAGES.map((stage, idx) => (
          <div className="stage-row" key={stage}>
            <span>{stage}</span>
            <div className="stage-bar">
              <div className="stage-fill" style={{ width: `${stageProgress[idx]}%` }} />
            </div>
          </div>
        ))}
      </div>

      <button type="submit" className="start-btn" disabled={submitting || !mediaPath || !projectId}>
        {submitting ? 'Starting...' : 'Start pipeline'}
      </button>
    </form>
  )
}
