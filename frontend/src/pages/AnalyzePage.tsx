import { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useApi } from '../api/apiContext'
import type { DocumentArtifact, MediaSubmissionPayload, SelectedProject, TranslationConfig } from '../api/runtimeApi'
import { MediaSubmitForm } from '../components/MediaSubmitForm'

export function AnalyzePage() {
  const navigate = useNavigate()
  const location = useLocation()
  const api = useApi()
  const [selectedProject, setSelectedProject] = useState<SelectedProject>({ project_id: null })
  const [submission, setSubmission] = useState<MediaSubmissionPayload | null>(null)
  const [translationConfig, setTranslationConfig] = useState<TranslationConfig | null>(null)
  const [artifacts, setArtifacts] = useState<DocumentArtifact[]>([])
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [liveProgress, setLiveProgress] = useState<number[]>([0, 0, 0, 0, 0])
  const selectedMedia = (location.state as
    | {
        selectedMedia?: {
          mediaFileId?: string
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
    if (!isSubmitting) return
    setLiveProgress([12, 0, 0, 0, 0])
    const timer = window.setInterval(() => {
      setLiveProgress((prev) => {
        const next = [...prev]
        if (next[0] < 100) {
          next[0] = Math.min(100, next[0] + 12)
          if (next[0] >= 70 && next[1] < 50) next[1] = 50
          return next
        }
        if (next[1] < 100) {
          next[1] = Math.min(100, next[1] + 9)
          if (next[1] >= 65 && next[2] < 45) next[2] = 45
          return next
        }
        if (next[2] < 100) {
          next[2] = Math.min(100, next[2] + 8)
          if (next[2] >= 65 && next[3] < 35) next[3] = 35
          return next
        }
        if (next[3] < 95) {
          next[3] = Math.min(95, next[3] + 6)
          if (next[3] >= 60 && next[4] < 25) next[4] = 25
          return next
        }
        if (next[4] < 90) {
          next[4] = Math.min(90, next[4] + 5)
          return next
        }
        return next
      })
    }, 450)
    return () => window.clearInterval(timer)
  }, [isSubmitting])

  useEffect(() => {
    if (!submission?.result.document_id) {
      setArtifacts([])
      return
    }
    api.listDocumentArtifacts(submission.result.document_id).then(setArtifacts).catch(() => setArtifacts([]))
  }, [api, submission?.result.document_id])

  const stageProgress = useMemo(() => {
    if (isSubmitting) return liveProgress
    if (!submission) return [0, 0, 0, 0, 0]
    if (submission.result.route === 'reject') return [100, 0, 0, 0, 0]
    if (submission.result.route === 'local') return [100, 100, 100, 100, 100]
    return [0, 0, 0, 0, 0]
  }, [submission, isSubmitting, liveProgress])

  return (
    <section className="screen-block analyze-stack">
      <MediaSubmitForm
        onSubmitted={(payload) => {
          setIsSubmitting(false)
          setSubmission(payload)
          setLiveProgress(payload.result.route === 'local' ? [100, 100, 100, 100, 100] : [100, 0, 0, 0, 0])
        }}
        onSubmittingChange={setIsSubmitting}
        projectId={selectedProject.project_id ?? null}
        projectLabel={selectedProject.project_name ?? selectedProject.project_id ?? 'Project'}
        stageProgress={stageProgress}
        initialMedia={selectedMedia}
        translatorOptions={translationConfig?.providers || []}
        defaultTranslator={translationConfig?.default_provider || 'm2m100'}
      />
      {submission ? (
        <section className={`card feedback ${submission.ui_feedback.severity}`} aria-label="submission-feedback">
          <p>{submission.ui_feedback.message}</p>
        </section>
      ) : null}
      {submission?.result.document_id ? (
        <section className="card compact-card" aria-label="analyze-open-visualizer">
          <button type="button" onClick={() => navigate('/visualizer', { state: { documentId: submission.result.document_id } })}>
            Open Visualizer
          </button>
          {artifacts.length > 0 ? (
            <div className="artifact-actions">
              {artifacts.map((artifact) => (
                <a key={artifact.name} className="top-link" href={artifact.download_url} target="_blank" rel="noreferrer">
                  Download {artifact.name}
                </a>
              ))}
            </div>
          ) : null}
        </section>
      ) : null}
    </section>
  )
}
