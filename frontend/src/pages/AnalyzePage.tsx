import { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useApi } from '../api/apiContext'
import type { BackendJobStatus, DocumentArtifact, MediaSubmissionPayload, SelectedProject, TranslationConfig } from '../api/runtimeApi'
import { MediaSubmitForm } from '../components/MediaSubmitForm'

export function AnalyzePage() {
  const navigate = useNavigate()
  const location = useLocation()
  const api = useApi()
  const [selectedProject, setSelectedProject] = useState<SelectedProject>({ project_id: null })
  const [submission, setSubmission] = useState<MediaSubmissionPayload | null>(null)
  const [translationConfig, setTranslationConfig] = useState<TranslationConfig | null>(null)
  const [artifacts, setArtifacts] = useState<DocumentArtifact[]>([])
  const [jobId, setJobId] = useState<string | null>(null)
  const [jobStatus, setJobStatus] = useState<BackendJobStatus | null>(null)
  const [liveProgress, setLiveProgress] = useState<number[]>([0, 0, 0, 0, 0])
  const [analysisStartedAt, setAnalysisStartedAt] = useState<number | null>(null)
  const [nowTs, setNowTs] = useState<number>(Date.now())
  const selectedMedia = (location.state as
    | {
        selectedMedia?: {
          mediaFileId?: string
          documentId?: string
          mediaPath?: string
          durationSec?: number
          sizeBytes?: number
          fileName?: string
        }
      }
    | null
    | undefined)?.selectedMedia

  useEffect(() => {
    api.getSelectedProject().then(setSelectedProject)
    api.getTranslationConfig().then(setTranslationConfig)
  }, [api])

  useEffect(() => {
    if (!jobId) return
    const ticker = window.setInterval(() => setNowTs(Date.now()), 1000)
    return () => window.clearInterval(ticker)
  }, [jobId])

  useEffect(() => {
    if (!jobId) return
    let stopped = false
    const poll = async () => {
      try {
        const status = await api.getBackendJobStatus(jobId)
        if (stopped) return
        setJobStatus(status)
        if (Array.isArray(status.stage_progress) && status.stage_progress.length === 5) {
          setLiveProgress(status.stage_progress)
        }
        if (status.status === 'completed_local' || status.status === 'rejected' || status.status === 'error' || status.status === 'not_found') {
          setJobId(null)
        }
      } catch {
        if (!stopped) setJobId(null)
      }
    }
    poll()
    const timer = window.setInterval(poll, 800)
    return () => {
      stopped = true
      window.clearInterval(timer)
    }
  }, [api, jobId])

  const activeDocumentId = jobStatus?.document_id || submission?.result.document_id || selectedMedia?.documentId
  const stageLogLines = (jobStatus?.stage_logs || []).slice(-10)

  useEffect(() => {
    if (!activeDocumentId) {
      setArtifacts([])
      return
    }
    let stopped = false
    const fetchArtifacts = async () => {
      try {
        const rows = await api.listDocumentArtifacts(activeDocumentId)
        if (!stopped) setArtifacts(rows)
      } catch {
        if (!stopped) setArtifacts([])
      }
    }
    fetchArtifacts()
    if (jobId) {
      const timer = window.setInterval(fetchArtifacts, 1200)
      return () => {
        stopped = true
        window.clearInterval(timer)
      }
    }
    return () => {
      stopped = true
    }
  }, [api, activeDocumentId, jobId, jobStatus?.status])

  const stageProgress = useMemo(() => {
    if (jobId) return liveProgress
    if (!submission) return [0, 0, 0, 0, 0]
    if (submission.result.route === 'reject') return [100, 0, 0, 0, 0]
    if (submission.result.route === 'local') return [100, 100, 100, 100, 100]
    return [0, 0, 0, 0, 0]
  }, [submission, jobId, liveProgress])

  const activeStageIndex = useMemo(() => {
    if (!jobId) return null
    for (let i = stageProgress.length - 1; i >= 0; i -= 1) {
      const value = Number(stageProgress[i] ?? 0)
      if (value > 0 && value < 100) return i
    }
    return null
  }, [jobId, stageProgress])
  const elapsedSec = useMemo(() => {
    if (!analysisStartedAt) return 0
    return Math.max(0, Math.floor((nowTs - analysisStartedAt) / 1000))
  }, [analysisStartedAt, nowTs])
  const estimatedSec = useMemo(() => {
    const progressValues = stageProgress.map((value) => {
      const n = Number(value)
      if (!Number.isFinite(n)) return 0
      return Math.max(0, Math.min(100, n))
    })
    const progressFraction = progressValues.reduce((acc, value) => acc + value, 0) / (progressValues.length * 100)
    if (elapsedSec > 0 && progressFraction >= 0.03) {
      return Math.max(elapsedSec + 1, Math.round(elapsedSec / Math.max(progressFraction, 0.03)))
    }
    const src = Number(selectedMedia?.durationSec ?? 0)
    if (src > 0) return Math.max(20, Math.round(src * 1.8))
    return 60
  }, [elapsedSec, stageProgress, selectedMedia?.durationSec])
  const stageTitle = useMemo(() => {
    const value = String(jobStatus?.stage_name || '').trim().toLowerCase()
    if (!value) return ''
    if (value === 'translating_text') return 'linguistic parsing'
    return value.replace(/_/g, ' ')
  }, [jobStatus?.stage_name])

  return (
    <section className="screen-block analyze-stack">
      <MediaSubmitForm
        onSubmitted={(payload) => {
          setSubmission(payload)
          setJobStatus(null)
          setAnalysisStartedAt(Date.now())
          setNowTs(Date.now())
          if (payload.result.route === 'local' && payload.result.status === 'accepted_local' && payload.result.job_id) {
            setJobId(payload.result.job_id)
            setLiveProgress([2, 0, 0, 0, 0])
          } else {
            setJobId(null)
            setLiveProgress(payload.result.route === 'local' ? [100, 100, 100, 100, 100] : [100, 0, 0, 0, 0])
          }
        }}
        onSubmittingChange={() => {}}
        projectId={selectedProject.project_id ?? null}
        projectLabel={selectedProject.project_name ?? selectedProject.project_id ?? 'Project'}
        stageProgress={stageProgress}
        activeStageIndex={activeStageIndex}
        initialMedia={selectedMedia}
        translatorOptions={translationConfig?.providers || []}
        defaultTranslator={translationConfig?.default_provider || 'm2m100'}
      />
      {submission ? (
        <section className={`card feedback ${submission.ui_feedback.severity}`} aria-label="submission-feedback">
          <p>{jobStatus?.message || submission.ui_feedback.message}</p>
          <p className="stage-log-title">Elapsed: {elapsedSec}s / Estimated: {estimatedSec}s</p>
          {stageTitle ? (
            <p className="stage-log-title">Stage: {stageTitle}</p>
          ) : null}
          {stageLogLines.length > 0 ? (
            <pre className="stage-log-box">{stageLogLines.join('\n')}</pre>
          ) : null}
        </section>
      ) : null}
      {activeDocumentId ? (
        <section className="card compact-card" aria-label="analyze-open-visualizer">
          <button type="button" onClick={() => navigate('/visualizer', { state: { documentId: activeDocumentId } })}>
            Open Visualizer
          </button>
          <p className="stage-log-title">Available artifacts</p>
          <div className="artifact-actions">
            {artifacts.length > 0 ? (
              artifacts.map((artifact) => (
                <a key={artifact.name} className="top-link" href={artifact.download_url} target="_blank" rel="noreferrer">
                  Download {artifact.name}
                </a>
              ))
            ) : (
              <span className="muted">Artifacts are not ready yet.</span>
            )}
          </div>
        </section>
      ) : null}
    </section>
  )
}
