import { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useApi } from '../api/apiContext'
import type { BackendJob, MediaSubmissionPayload, SelectedProject } from '../api/runtimeApi'
import { BackendJobsTable } from '../components/BackendJobsTable'
import { MediaSubmitForm } from '../components/MediaSubmitForm'

export function AnalyzePage() {
  const navigate = useNavigate()
  const location = useLocation()
  const api = useApi()
  const [selectedProject, setSelectedProject] = useState<SelectedProject>({ project_id: null })
  const [jobs, setJobs] = useState<BackendJob[]>([])
  const [submission, setSubmission] = useState<MediaSubmissionPayload | null>(null)
  const [activeJobId, setActiveJobId] = useState<string | null>(null)
  const [activeJobStatus, setActiveJobStatus] = useState<string>('')
  const [syncMessage, setSyncMessage] = useState<string>('')
  const [syncedDocumentId, setSyncedDocumentId] = useState<string | null>(null)
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
    api.listBackendJobs().then(setJobs)
  }, [api])

  async function refreshJobs() {
    const updated = await api.listBackendJobs()
    setJobs(updated)
  }

  async function pollActiveJob() {
    if (!activeJobId) return
    const status = await api.getBackendJobStatus(activeJobId)
    setActiveJobStatus(status.status)
    await refreshJobs()
    if (status.status === 'completed') {
      const synced = await api.syncBackendResult(activeJobId)
      setSyncMessage(synced.message || '')
      setSyncedDocumentId(synced.document_id || null)
      await refreshJobs()
    }
  }

  async function retryActiveJob() {
    if (!activeJobId) return
    const result = await api.retryBackendJob(activeJobId)
    setActiveJobStatus(result.status)
    setSyncMessage(result.message || '')
    setSyncedDocumentId(null)
    await refreshJobs()
  }

  async function resumeJobs() {
    const resumed = await api.resumeBackendJobs()
    if (resumed.jobs.length > 0 && !activeJobId) {
      setActiveJobId(resumed.jobs[0].job_id)
      setActiveJobStatus(resumed.jobs[0].status)
    }
    await refreshJobs()
  }

  useEffect(() => {
    if (!activeJobId) return
    if (['completed', 'failed', 'error', 'canceled', 'rejected', 'not_found'].includes(activeJobStatus)) return
    const timer = window.setInterval(() => {
      pollActiveJob()
    }, 2500)
    return () => window.clearInterval(timer)
  }, [activeJobId, activeJobStatus])

  const projectJobs = jobs.filter((job) => {
    if (!selectedProject.project_id) return true
    return !job.project_id || job.project_id === selectedProject.project_id
  })

  const stageProgress = useMemo(() => {
    if (!submission) return [0, 0, 0, 0, 0]
    if (submission.result.route === 'reject') return [100, 0, 0, 0, 0]
    if (submission.result.route === 'local') return [100, 100, 100, 100, 100]
    if (activeJobStatus === 'queued') return [100, 35, 0, 0, 0]
    if (activeJobStatus === 'processing') return [100, 100, 80, 45, 0]
    if (activeJobStatus === 'completed') return [100, 100, 100, 100, 100]
    if (['failed', 'error', 'canceled', 'rejected'].includes(activeJobStatus)) return [100, 100, 55, 0, 0]
    return [100, 100, 100, 35, 0]
  }, [submission, activeJobStatus])

  return (
    <section className="screen-block analyze-stack">
      <MediaSubmitForm
        onSubmitted={(payload) => {
          setSubmission(payload)
          setSyncMessage('')
          setSyncedDocumentId(null)
          setActiveJobId(payload.result.job_id || null)
          setActiveJobStatus(payload.result.route === 'backend' ? 'queued' : payload.result.route)
          api.listBackendJobs().then(setJobs)
        }}
        projectId={selectedProject.project_id ?? null}
        projectLabel={selectedProject.project_name ?? selectedProject.project_id ?? 'Project'}
        stageProgress={stageProgress}
        initialMedia={selectedMedia}
      />
      {submission ? (
        <section className={`card feedback ${submission.ui_feedback.severity}`} aria-label="submission-feedback">
          <p>{submission.ui_feedback.message}</p>
        </section>
      ) : null}
      {activeJobId ? (
        <section className="card compact-card" aria-label="backend-job-controls">
          <p>
            Job ID: <strong>{activeJobId}</strong> | Status: <strong>{activeJobStatus || 'unknown'}</strong>
          </p>
          <div className="job-actions">
            <button type="button" onClick={pollActiveJob}>
              Check status
            </button>
            <button type="button" onClick={retryActiveJob}>
              Retry
            </button>
            <button type="button" onClick={resumeJobs}>
              Resume
            </button>
            {syncedDocumentId ? (
              <button type="button" onClick={() => navigate('/visualizer', { state: { documentId: syncedDocumentId } })}>
                Open Visualizer
              </button>
            ) : null}
          </div>
          {syncMessage ? <p>{syncMessage}</p> : null}
        </section>
      ) : null}
      <BackendJobsTable jobs={projectJobs} />
    </section>
  )
}
