import { useEffect, useMemo, useState } from 'react'
import { useApi } from '../api/apiContext'
import type { MediaSubmissionPayload } from '../api/runtimeApi'

type Props = {
  onSubmitted: (payload: MediaSubmissionPayload) => void
  projectId: string | null
  projectLabel: string
  initialMedia?: {
    mediaFileId?: string
    mediaPath?: string
    durationSec?: number
    sizeBytes?: number
    fileName?: string
  }
}

const STAGES = ['Loading file', 'Transcribing audio', 'Translating text', 'Generating media', 'Exporting files']

export function MediaSubmitForm({ onSubmitted, projectId, projectLabel, initialMedia }: Props) {
  const api = useApi()
  const [mediaPath, setMediaPath] = useState('')
  const [durationSec, setDurationSec] = useState(600)
  const [sizeBytes, setSizeBytes] = useState(100 * 1024 * 1024)
  const [mediaFileId, setMediaFileId] = useState<string | undefined>(undefined)
  const [selectedFileName, setSelectedFileName] = useState('')
  const [translator, setTranslator] = useState('GPT')
  const [subtitles, setSubtitles] = useState('Bilingual')
  const [voice, setVoice] = useState('Male')
  const [submitting, setSubmitting] = useState(false)
  const [lastRoute, setLastRoute] = useState<'local' | 'backend' | 'reject' | null>(null)

  useEffect(() => {
    if (!initialMedia) return
    if (initialMedia.mediaPath) setMediaPath(initialMedia.mediaPath)
    if (typeof initialMedia.durationSec === 'number') setDurationSec(initialMedia.durationSec)
    if (typeof initialMedia.sizeBytes === 'number') setSizeBytes(initialMedia.sizeBytes)
    setMediaFileId(initialMedia.mediaFileId)
    setSelectedFileName(initialMedia.fileName ?? '')
  }, [initialMedia])

  const stageProgress = useMemo(() => {
    if (!lastRoute) return [0, 0, 0, 0, 0]
    if (lastRoute === 'reject') return [100, 0, 0, 0, 0]
    if (lastRoute === 'backend') return [100, 100, 100, 35, 0]
    return [100, 100, 100, 100, 100]
  }, [lastRoute])

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
      })
      setLastRoute(payload.result.route)
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
        <select className="flat-select" value={translator} onChange={(e) => setTranslator(e.target.value)}>
          <option>GPT</option>
          <option>HF</option>
        </select>

        <label className="analyze-label">Subtitles:</label>
        <select className="flat-select" value={subtitles} onChange={(e) => setSubtitles(e.target.value)}>
          <option>Bilingual</option>
          <option>Target only</option>
          <option>Source only</option>
        </select>

        <label className="analyze-label">Voice:</label>
        <select className="flat-select" value={voice} onChange={(e) => setVoice(e.target.value)}>
          <option>Male</option>
          <option>Female</option>
        </select>
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

