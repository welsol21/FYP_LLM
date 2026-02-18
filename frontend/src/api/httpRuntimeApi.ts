import type {
  BackendJob,
  BackendJobStatus,
  BackendResumePayload,
  BackendSyncPayload,
  MediaFileRow,
  MediaSubmissionPayload,
  RuntimeApi,
  RuntimeUiState,
  VisualizerPayload,
} from './runtimeApi'

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init)
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`HTTP ${res.status}: ${text}`)
  }
  return (await res.json()) as T
}

export class HttpRuntimeApi implements RuntimeApi {
  async getUiState(): Promise<RuntimeUiState> {
    return requestJson<RuntimeUiState>('/api/ui-state')
  }

  async uploadMedia(file: File): Promise<{ fileName: string; mediaPath: string; sizeBytes: number }> {
    const form = new FormData()
    form.append('file', file, file.name)
    const res = await fetch('/api/upload', { method: 'POST', body: form })
    if (!res.ok) {
      const text = await res.text()
      throw new Error(`HTTP ${res.status}: ${text}`)
    }
    return (await res.json()) as { fileName: string; mediaPath: string; sizeBytes: number }
  }

  async submitMedia(input: {
    mediaPath: string
    durationSec: number
    sizeBytes: number
    projectId?: string
    mediaFileId?: string
  }): Promise<MediaSubmissionPayload> {
    return requestJson<MediaSubmissionPayload>('/api/submit-media', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    })
  }

  async listBackendJobs(): Promise<BackendJob[]> {
    return requestJson<BackendJob[]>('/api/backend-jobs')
  }

  async getBackendJobStatus(jobId: string): Promise<BackendJobStatus> {
    return requestJson<BackendJobStatus>(`/api/backend-job-status?job_id=${encodeURIComponent(jobId)}`)
  }

  async retryBackendJob(jobId: string): Promise<BackendSyncPayload> {
    return requestJson<BackendSyncPayload>('/api/retry-backend-job', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ jobId }),
    })
  }

  async resumeBackendJobs(): Promise<BackendResumePayload> {
    return requestJson<BackendResumePayload>('/api/resume-backend-jobs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    })
  }

  async syncBackendResult(jobId: string): Promise<BackendSyncPayload> {
    return requestJson<BackendSyncPayload>('/api/sync-backend-result', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ jobId }),
    })
  }

  async listFiles(projectId?: string): Promise<MediaFileRow[]> {
    const suffix = projectId ? `?project_id=${encodeURIComponent(projectId)}` : ''
    return requestJson<MediaFileRow[]>(`/api/files${suffix}`)
  }

  async getVisualizerPayload(documentId?: string): Promise<VisualizerPayload> {
    if (!documentId) return {}
    return requestJson<VisualizerPayload>(`/api/visualizer-payload?document_id=${encodeURIComponent(documentId)}`)
  }

  async applyEdit(input: {
    sentenceText: string
    nodeId: string
    fieldPath: string
    newValue: string
    documentId?: string
  }): Promise<{ status: 'ok' | 'error'; message: string }> {
    return requestJson<{ status: 'ok' | 'error'; message: string }>('/api/apply-edit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    })
  }
}
