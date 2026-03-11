import { useEffect, useRef, useState } from 'react'
import { useApi } from '../api/apiContext'
import type { MediaProgressPayload, MediaSubmissionPayload, TranslationProviderConfig } from '../api/runtimeApi'

type Props = {
  onSubmitted: (payload: MediaSubmissionPayload) => void
  onProgress?: (payload: MediaProgressPayload) => void
  onSubmittingChange?: (value: boolean) => void
  projectId: string | null
  projectLabel: string
  stageProgress: number[]
  activeStageIndex?: number | null
  isAnalyzing?: boolean
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

const STAGES = ['Loading file', 'Transcribing audio', 'Linguistic parsing', 'Generating media', 'Exporting files']

function hasRequiredCredentials(provider: TranslationProviderConfig): boolean {
  if (!provider.credential_fields.length) return true
  return provider.credential_fields.every((field) => String(provider.credentials[field] || '').trim().length > 0)
}

export function MediaSubmitForm({
  onSubmitted,
  onProgress,
  onSubmittingChange,
  projectId,
  projectLabel,
  stageProgress,
  activeStageIndex = null,
  isAnalyzing = false,
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
  const [subtitles, setSubtitles] = useState('Bilingual (sequential)')
  const [voice, setVoice] = useState('Male')
  const [processingMode, setProcessingMode] = useState<'incremental' | 'force'>('incremental')
  const [submitting, setSubmitting] = useState(false)
  const currentControllerRef = useRef<AbortController | null>(null)
  const enabledProviders = translatorOptions.filter((p) => p.enabled && hasRequiredCredentials(p))
  const subtitleOptions: Array<{ label: string; value: string }> = [
    { label: 'Bilingual (sequential)', value: 'bilingual_sequential' },
    { label: 'Bilingual (simultaneous)', value: 'bilingual_simultaneous' },
    { label: 'Target only', value: 'target only' },
    { label: 'Source only', value: 'source only' },
  ]
  const online = typeof navigator !== 'undefined' ? navigator.onLine : true
  const voiceOptions: Array<{ label: string; value: string }> = online
    ? [
        { label: 'Male', value: 'client_male' },
        { label: 'Dmitry (Male)', value: 'backend_dmitry' },
        { label: 'Svetlana (Female)', value: 'backend_svetlana' },
      ]
    : [{ label: 'Male', value: 'client_male' }]
  const normalizedProjectLabel = String(projectLabel || '').trim()
  const showProjectLine = normalizedProjectLabel.length > 0 && normalizedProjectLabel !== '-'
  const normalizedFileLabel = String(selectedFileName || '').trim()
  const showFileLine = normalizedFileLabel.length > 0 && normalizedFileLabel !== '-'

  useEffect(() => {
    if (!initialMedia) {
      setMediaPath('')
      setDurationSec(600)
      setSizeBytes(100 * 1024 * 1024)
      setMediaFileId(undefined)
      setSelectedFileName('')
      return
    }
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
    if (!voiceOptions.some((option) => option.label === voice)) {
      setVoice(voiceOptions[0]?.label || 'Male')
    }
  }, [voice, voiceOptions])

  useEffect(() => {
    if (!enabledProviders.length) return
    const hasCurrent = enabledProviders.some((p) => p.id === translator)
    if (!hasCurrent) setTranslator(enabledProviders[0].id)
  }, [enabledProviders, translator])

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const controller = new AbortController()
    currentControllerRef.current = controller
    setSubmitting(true)
    onSubmittingChange?.(true)
    try {
      const payload = await api.submitMedia({
        mediaPath,
        durationSec,
        sizeBytes,
        projectId: projectId ?? undefined,
        mediaFileId,
        translationProvider: translator,
        subtitlesMode: subtitleOptions.find((option) => option.label === subtitles)?.value || 'bilingual_sequential',
        voiceChoice: voiceOptions.find((option) => option.label === voice)?.value || 'male',
        forceFullReprocess: processingMode === 'force',
        onProgress,
        signal: controller.signal,
      })
      if (controller.signal.aborted || currentControllerRef.current !== controller) return
      onSubmitted(payload)
    } catch (err) {
      if (!(err instanceof DOMException && err.name === 'AbortError')) throw err
    } finally {
      if (currentControllerRef.current === controller) {
        currentControllerRef.current = null
        setSubmitting(false)
        onSubmittingChange?.(false)
      }
    }
  }

  function handleCancel(): void {
    currentControllerRef.current?.abort()
    currentControllerRef.current = null
    setSubmitting(false)
    onSubmittingChange?.(false)
    onSubmitted({
      result: {
        route: 'reject',
        message: 'Analysis cancelled.',
        status: 'cancelled',
        stage_name: 'completed',
      },
      ui_feedback: {
        severity: 'warning',
        title: 'Processing cancelled',
        message: 'Analysis cancelled.',
      },
    })
  }

  return (
    <form onSubmit={handleSubmit} className="analyze-panel" aria-label="media-submit-form">
      {showProjectLine ? <div className="project-line">{normalizedProjectLabel}</div> : null}
      {showFileLine ? <div className="file-line">{normalizedFileLabel}</div> : null}

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
              key={option.value}
              type="button"
              className={`touch-option-btn${subtitles === option.label ? ' active' : ''}`}
              onClick={() => setSubtitles(option.label)}
            >
              {option.label}
            </button>
          ))}
        </div>

        <label className="analyze-label">Voice:</label>
        <div className="touch-options-grid">
          {voiceOptions.map((option) => (
            <button
              key={option.value}
              type="button"
              className={`touch-option-btn${voice === option.label ? ' active' : ''}`}
              onClick={() => setVoice(option.label)}
            >
              {option.label}
            </button>
          ))}
        </div>

        <label className="analyze-label">Processing:</label>
        <div className="touch-options-grid">
          <button
            type="button"
            className={`touch-option-btn${processingMode === 'incremental' ? ' active' : ''}`}
            onClick={() => setProcessingMode('incremental')}
          >
            Incremental reuse
          </button>
          <button
            type="button"
            className={`touch-option-btn${processingMode === 'force' ? ' active' : ''}`}
            onClick={() => setProcessingMode('force')}
          >
            Force full reprocess
          </button>
        </div>
      </div>

      <div className="stage-list">
        {STAGES.map((stage, idx) => (
          <div className="stage-row" key={stage}>
            <span>{stage}</span>
            <div className="stage-bar">
              <div
                className={`stage-fill${activeStageIndex === idx ? " active" : ""}`}
                style={{ width: `${stageProgress[idx]}%` }}
              />
            </div>
          </div>
        ))}
      </div>

      {submitting || isAnalyzing ? (
        <button type="button" className="start-btn cancel-btn" onClick={handleCancel}>
          Cancel
        </button>
      ) : (
        <button type="submit" className="start-btn" disabled={!mediaPath || !projectId}>
          Start pipeline
        </button>
      )}
    </form>
  )
}
