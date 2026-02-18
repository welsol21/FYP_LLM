export type RuntimeUiState = {
  runtime_mode: string
  deployment_mode: string
  badges: Record<string, string>
  features: {
    phonetic: { enabled: boolean; reason_if_disabled: string }
    db_persistence: { enabled: boolean; reason_if_disabled: string }
    backend_jobs: { enabled: boolean; reason_if_disabled: string }
  }
}

export type ProjectRow = {
  id: string
  name: string
  created_at: string
  updated_at: string
}

export type SelectedProject = {
  project_id: string | null
  project_name?: string
}

export type MediaSubmissionPayload = {
  result: {
    route: 'local' | 'backend' | 'reject'
    message: string
    job_id?: string
  }
  ui_feedback: {
    severity: 'info' | 'warning' | 'error'
    title: string
    message: string
  }
}

export type BackendJob = {
  id: string
  status: string
  media_path: string
  duration_seconds: number
  size_bytes: number
}

export type BackendJobStatus = {
  job_id: string
  status: string
  updated_at?: string
  project_id?: string
  media_file_id?: string
}

export type BackendResumePayload = {
  resumed_count: number
  jobs: BackendJobStatus[]
}

export type BackendSyncPayload = {
  job_id: string
  status: string
  document_id?: string
  message?: string
}

export type MediaFileRow = {
  id: string
  name: string
  settings: string
  updated: string
  analyzed: boolean
  document_id?: string
}

export type VisualizerNode = {
  node_id: string
  type: string
  content: string
  tense: string
  linguistic_notes: string[]
  notes?: Array<{ text?: string }>
  part_of_speech: string
  linguistic_elements: VisualizerNode[]
  cefr_level?: string
  phonetic?: { uk?: string; us?: string }
  translation?: {
    source_lang?: string
    target_lang?: string
    text: string
    model?: string
  }
}

export type VisualizerPayload = Record<string, VisualizerNode>

export interface RuntimeApi {
  getUiState(): Promise<RuntimeUiState>
  listProjects(): Promise<ProjectRow[]>
  createProject(name: string): Promise<ProjectRow>
  getSelectedProject(): Promise<SelectedProject>
  setSelectedProject(projectId: string): Promise<SelectedProject>
  uploadMedia(file: File): Promise<{ fileName: string; mediaPath: string; sizeBytes: number }>
  submitMedia(input: {
    mediaPath: string
    durationSec: number
    sizeBytes: number
    projectId?: string
    mediaFileId?: string
  }): Promise<MediaSubmissionPayload>
  listBackendJobs(): Promise<BackendJob[]>
  getBackendJobStatus(jobId: string): Promise<BackendJobStatus>
  retryBackendJob(jobId: string): Promise<BackendSyncPayload>
  resumeBackendJobs(): Promise<BackendResumePayload>
  syncBackendResult(jobId: string): Promise<BackendSyncPayload>
  listFiles(projectId?: string): Promise<MediaFileRow[]>
  getVisualizerPayload(documentId?: string): Promise<VisualizerPayload>
  applyEdit(input: {
    sentenceText: string
    nodeId: string
    fieldPath: string
    newValue: string
    documentId?: string
  }): Promise<{ status: 'ok' | 'error'; message: string }>
}
