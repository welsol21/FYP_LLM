import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useApi } from '../api/apiContext'
import type { BackendJob, MediaSubmissionPayload, RuntimeUiState } from '../api/runtimeApi'
import { BackendJobsTable } from '../components/BackendJobsTable'
import { MediaSubmitForm } from '../components/MediaSubmitForm'
import { RuntimeStatusCard } from '../components/RuntimeStatusCard'

export function AnalyzePage() {
  const navigate = useNavigate()
  const api = useApi()
  const [uiState, setUiState] = useState<RuntimeUiState | null>(null)
  const [submission, setSubmission] = useState<MediaSubmissionPayload | null>(null)
  const [jobs, setJobs] = useState<BackendJob[]>([])
  const [activeJobId, setActiveJobId] = useState<string | null>(null)
  const [activeJobStatus, setActiveJobStatus] = useState<string>('')
  const [syncMessage, setSyncMessage] = useState<string>('')
  const [syncedDocumentId, setSyncedDocumentId] = useState<string | null>(null)

  useEffect(() => {
    api.getUiState().then(setUiState)
    api.listBackendJobs().then(setJobs)
  }, [api])

  async function onSubmitted(payload: MediaSubmissionPayload) {
    setSubmission(payload)
    setSyncMessage('')
    setSyncedDocumentId(null)
    setActiveJobId(payload.result.job_id || null)
    setActiveJobStatus(payload.result.route === 'backend' ? 'queued' : '')
    const updated = await api.listBackendJobs()
    setJobs(updated)
  }

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
    if (activeJobStatus === 'completed') return
    const timer = window.setInterval(() => {
      pollActiveJob()
    }, 2500)
    return () => window.clearInterval(timer)
  }, [activeJobId, activeJobStatus])

  return (
    <section>
      <RuntimeStatusCard uiState={uiState} />
      <MediaSubmitForm onSubmitted={onSubmitted} />
      {submission ? (
        <section className={`card feedback ${submission.ui_feedback.severity}`} aria-label="submission-feedback">
          <h2>{submission.ui_feedback.title}</h2>
          <p>{submission.ui_feedback.message}</p>
        </section>
      ) : null}
      {activeJobId ? (
        <section className="card compact-card" aria-label="backend-job-controls">
          <h2>Backend Processing</h2>
          <p>
            Active Job: <strong>{activeJobId}</strong> | Status: <strong>{activeJobStatus || 'unknown'}</strong>
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
              <button
                type="button"
                onClick={() => navigate('/visualizer', { state: { documentId: syncedDocumentId } })}
              >
                Open Visualizer
              </button>
            ) : null}
          </div>
          {syncMessage ? <p>{syncMessage}</p> : null}
        </section>
      ) : null}
      <BackendJobsTable jobs={jobs} />
    </section>
  )
}
