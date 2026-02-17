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

export type VisualizerNode = {
  node_id: string
  type: string
  content: string
  part_of_speech?: string
  phraseType?: string
  cefr_level?: string
  tense?: string
  phonetic?: { uk?: string; us?: string }
  linguistic_notes?: string[]
  translation?: {
    source_lang?: string
    target_lang?: string
    text: string
    model?: string
  }
  children: VisualizerNode[]
}

export type VisualizerPayloadRow = {
  sentence_text: string
  tree: VisualizerNode
}

export interface RuntimeApi {
  getUiState(): Promise<RuntimeUiState>
  submitMedia(input: {
    mediaPath: string
    durationSec: number
    sizeBytes: number
    projectId?: string
    mediaFileId?: string
  }): Promise<MediaSubmissionPayload>
  listBackendJobs(): Promise<BackendJob[]>
  getVisualizerPayload(): Promise<VisualizerPayloadRow[]>
  applyEdit(input: {
    sentenceText: string
    nodeId: string
    fieldPath: string
    newValue: string
  }): Promise<{ status: 'ok' | 'error'; message: string }>
}
