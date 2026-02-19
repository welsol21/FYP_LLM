import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { useApi } from '../api/apiContext'
import type { BackendJob, MediaSubmissionPayload, SelectedProject } from '../api/runtimeApi'
import { BackendJobsTable } from '../components/BackendJobsTable'
import { MediaSubmitForm } from '../components/MediaSubmitForm'

export function AnalyzePage() {
  const location = useLocation()
  const api = useApi()
  const [selectedProject, setSelectedProject] = useState<SelectedProject>({ project_id: null })
  const [jobs, setJobs] = useState<BackendJob[]>([])
  const [submission, setSubmission] = useState<MediaSubmissionPayload | null>(null)
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

  const projectJobs = jobs.filter((job) => {
    if (!selectedProject.project_id) return true
    return !job.project_id || job.project_id === selectedProject.project_id
  })

  return (
    <section className="screen-block analyze-stack">
      <MediaSubmitForm
        onSubmitted={(payload) => {
          setSubmission(payload)
          api.listBackendJobs().then(setJobs)
        }}
        projectId={selectedProject.project_id ?? null}
        projectLabel={selectedProject.project_name ?? selectedProject.project_id ?? 'Project'}
        initialMedia={selectedMedia}
      />
      {submission ? (
        <section className={`card feedback ${submission.ui_feedback.severity}`} aria-label="submission-feedback">
          <p>{submission.ui_feedback.message}</p>
        </section>
      ) : null}
      <BackendJobsTable jobs={projectJobs} />
    </section>
  )
}
