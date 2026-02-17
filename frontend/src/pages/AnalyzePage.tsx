import { useEffect, useState } from 'react'
import { useApi } from '../api/apiContext'
import type { BackendJob, MediaSubmissionPayload, RuntimeUiState } from '../api/runtimeApi'
import { BackendJobsTable } from '../components/BackendJobsTable'
import { MediaSubmitForm } from '../components/MediaSubmitForm'
import { RuntimeStatusCard } from '../components/RuntimeStatusCard'

export function AnalyzePage() {
  const api = useApi()
  const [uiState, setUiState] = useState<RuntimeUiState | null>(null)
  const [submission, setSubmission] = useState<MediaSubmissionPayload | null>(null)
  const [jobs, setJobs] = useState<BackendJob[]>([])

  useEffect(() => {
    api.getUiState().then(setUiState)
    api.listBackendJobs().then(setJobs)
  }, [api])

  async function onSubmitted(payload: MediaSubmissionPayload) {
    setSubmission(payload)
    const updated = await api.listBackendJobs()
    setJobs(updated)
  }

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
      <BackendJobsTable jobs={jobs} />
    </section>
  )
}
