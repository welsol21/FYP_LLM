import { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useApi } from '../api/apiContext'
import type { MediaSubmissionPayload, SelectedProject, TranslationConfig } from '../api/runtimeApi'
import { MediaSubmitForm } from '../components/MediaSubmitForm'

export function AnalyzePage() {
  const navigate = useNavigate()
  const location = useLocation()
  const api = useApi()
  const [selectedProject, setSelectedProject] = useState<SelectedProject>({ project_id: null })
  const [submission, setSubmission] = useState<MediaSubmissionPayload | null>(null)
  const [translationConfig, setTranslationConfig] = useState<TranslationConfig | null>(null)
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

  const stageProgress = useMemo(() => {
    if (!submission) return [0, 0, 0, 0, 0]
    if (submission.result.route === 'reject') return [100, 0, 0, 0, 0]
    if (submission.result.route === 'local') return [100, 100, 100, 100, 100]
    return [0, 0, 0, 0, 0]
  }, [submission])

  return (
    <section className="screen-block analyze-stack">
      <MediaSubmitForm
        onSubmitted={(payload) => {
          setSubmission(payload)
        }}
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
        </section>
      ) : null}
    </section>
  )
}
