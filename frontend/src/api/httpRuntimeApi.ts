import type {
  MediaFileRow,
  MediaSubmissionPayload,
  ProjectRow,
  RuntimeApi,
  RuntimeUiState,
  SelectedProject,
  TranslationConfig,
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

  async listProjects(): Promise<ProjectRow[]> {
    return requestJson<ProjectRow[]>('/api/projects')
  }

  async createProject(name: string): Promise<ProjectRow> {
    return requestJson<ProjectRow>('/api/projects', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    })
  }

  async getSelectedProject(): Promise<SelectedProject> {
    return requestJson<SelectedProject>('/api/selected-project')
  }

  async setSelectedProject(projectId: string): Promise<SelectedProject> {
    return requestJson<SelectedProject>('/api/selected-project', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ projectId }),
    })
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

  async registerMediaFile(input: {
    projectId: string
    name: string
    mediaPath: string
    sizeBytes: number
    durationSec?: number
  }): Promise<{ id: string; project_id: string; name: string; path: string; size_bytes?: number; duration_seconds?: number }> {
    return requestJson<{ id: string; project_id: string; name: string; path: string; size_bytes?: number; duration_seconds?: number }>(
      '/api/register-media',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(input),
      },
    )
  }

  async submitMedia(input: {
    mediaPath: string
    durationSec: number
    sizeBytes: number
    projectId?: string
    mediaFileId?: string
    translationProvider?: string
    subtitlesMode?: string
    voiceChoice?: string
  }): Promise<MediaSubmissionPayload> {
    return requestJson<MediaSubmissionPayload>('/api/submit-media', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    })
  }

  async getTranslationConfig(): Promise<TranslationConfig> {
    return requestJson<TranslationConfig>('/api/translation-config')
  }

  async saveTranslationConfig(config: TranslationConfig): Promise<TranslationConfig> {
    return requestJson<TranslationConfig>('/api/translation-config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ config }),
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
