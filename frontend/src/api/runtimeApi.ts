export type RuntimeUiState = {
  runtime_mode: string
  deployment_mode: string
  badges: Record<string, string>
  features: {
    phonetic: { enabled: boolean; reason_if_disabled: string }
    db_persistence: { enabled: boolean; reason_if_disabled: string }
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
    route: 'local' | 'reject'
    message: string
    job_id?: string
    document_id?: string
    status?: string
  }
  ui_feedback: {
    severity: 'info' | 'warning' | 'error'
    title: string
    message: string
  }
}

export type DocumentArtifact = {
  name: string
  size_bytes: number
  download_url: string
}

export type BackendJobStatus = {
  job_id: string
  status: string
  message: string
  stage_name?: string
  stage_log?: string
  stage_logs?: string[]
  stage_progress: number[]
  document_id?: string
}

export type MediaFileRow = {
  id: string
  name: string
  path?: string
  size_bytes?: number
  duration_seconds?: number
  settings: string
  updated: string
  analyzed: boolean
  document_id?: string
}

export type AnalysisHistoryRow = {
  analysis_id: string
  document_id: string
  project_id: string
  project_name: string
  media_file_id?: string | null
  file_name: string
  file_path?: string
  size_bytes?: number
  duration_seconds?: number
  settings: string
  updated_at: string
  created_at: string
  contract_current?: boolean
}

export type VisualizerNode = {
  node_id: string
  type: string
  content: string
  source_span?: { start: number; end: number }
  tense: string
  linguistic_notes: {
    elementary: string
    intermediate: string
    advanced: string
  } | string[]
  notes?: Array<{ text?: string }>
  part_of_speech: string
  linguistic_elements: VisualizerNode[]
  cefr_level?: string
  phonetic?: { uk?: string; us?: string }
  active_translation_provider?: string
  translations: Record<
    string,
    {
      text: string
      source_lang?: string
      target_lang?: string
      created_at?: string
      origin?: string
    }
  >
}

export type VisualizerPayload = Record<string, VisualizerNode>

export type RazborNotes = {
  elementary: string
  intermediate: string
  advanced: string
}

export type RazborItem = {
  id: string | number
  input: string
  analysis: Record<string, unknown>
  notes: RazborNotes
  cefr_level?: string
}

export type AnalyzeTextPayload = {
  raw_text: string
  sentences: string[]
  razbor: RazborItem[]
  contract: VisualizerPayload
  notes_sources?: string[]
}

export type TranslationProviderConfig = {
  id: string
  label: string
  kind: 'builtin' | 'custom' | string
  enabled: boolean
  credential_fields: string[]
  credentials: Record<string, string>
}

export type TranslationConfig = {
  default_provider: string
  providers: TranslationProviderConfig[]
}

export interface RuntimeApi {
  getUiState(): Promise<RuntimeUiState>
  listProjects(): Promise<ProjectRow[]>
  createProject(name: string): Promise<ProjectRow>
  getSelectedProject(): Promise<SelectedProject>
  setSelectedProject(projectId: string): Promise<SelectedProject>
  uploadMedia(file: File): Promise<{ fileName: string; mediaPath: string; sizeBytes: number }>
  registerMediaFile(input: {
    projectId: string
    name: string
    mediaPath: string
    sizeBytes: number
    durationSec?: number
  }): Promise<{ id: string; project_id: string; name: string; path: string; size_bytes?: number; duration_seconds?: number }>
  submitMedia(input: {
    mediaPath: string
    durationSec: number
    sizeBytes: number
    projectId?: string
    mediaFileId?: string
    translationProvider?: string
    subtitlesMode?: string
    voiceChoice?: string
    forceFullReprocess?: boolean
  }): Promise<MediaSubmissionPayload>
  getTranslationConfig(): Promise<TranslationConfig>
  saveTranslationConfig(config: TranslationConfig): Promise<TranslationConfig>
  listFiles(projectId?: string): Promise<MediaFileRow[]>
  listAnalysisHistory(projectId?: string): Promise<AnalysisHistoryRow[]>
  deleteAnalysis(documentId: string): Promise<{ status: 'ok' | 'error'; message: string; document_id?: string }>
  listDocumentArtifacts(documentId: string): Promise<DocumentArtifact[]>
  getBackendJobStatus(jobId: string): Promise<BackendJobStatus>
  getVisualizerPayload(documentId?: string): Promise<VisualizerPayload>
  analyzeText(input: { rawText: string; sentences?: string[] }): Promise<AnalyzeTextPayload>
  applyEdit(input: {
    sentenceText: string
    nodeId: string
    fieldPath: string
    newValue: string
    documentId?: string
  }): Promise<{ status: 'ok' | 'error'; message: string }>
}
