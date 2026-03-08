import type {
  AnalysisHistoryRow,
  AnalyzeTextPayload,
  BackendJobStatus,
  DocumentArtifact,
  MediaFileRow,
  MediaSubmissionPayload,
  ProjectRow,
  RuntimeApi,
  RuntimeUiState,
  SelectedProject,
  TranslationConfig,
  VisualizerPayload,
} from './runtimeApi'
import { LocalWorkspace } from '../lib/localWorkspace'

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init)
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`HTTP ${res.status}: ${text}`)
  }
  return (await res.json()) as T
}

export class HttpRuntimeApi implements RuntimeApi {
  private readonly pendingJobs = new Map<string, {
    projectId: string
    mediaFileId?: string
    mediaPath: string
    sizeBytes?: number
    durationSec?: number
    settings: string
    fileName: string
  }>()

  private readonly finalizedDocuments = new Set<string>()

  async getUiState(): Promise<RuntimeUiState> {
    return requestJson<RuntimeUiState>('/api/ui-state')
  }

  async listProjects(): Promise<ProjectRow[]> {
    return LocalWorkspace.listProjects()
  }

  async createProject(name: string): Promise<ProjectRow> {
    return LocalWorkspace.createProject(name)
  }

  async getSelectedProject(): Promise<SelectedProject> {
    return LocalWorkspace.getSelectedProject()
  }

  async setSelectedProject(projectId: string): Promise<SelectedProject> {
    return LocalWorkspace.setSelectedProject(projectId)
  }

  async uploadMedia(file: File): Promise<{ fileName: string; mediaPath: string; sizeBytes: number }> {
    const form = new FormData()
    form.append('file', file, file.name)
    const res = await fetch('/api/upload', { method: 'POST', body: form })
    if (!res.ok) {
      if (res.status === 413) {
        throw new Error('Upload rejected: file is too large for current upload limit.')
      }
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
    const row = LocalWorkspace.registerMediaFile(input)
    return {
      id: row.id,
      project_id: row.project_id,
      name: row.name,
      path: row.path || row.media_path,
      size_bytes: row.size_bytes,
      duration_seconds: row.duration_seconds,
    }
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
    forceFullReprocess?: boolean
  }): Promise<MediaSubmissionPayload> {
    const selected = LocalWorkspace.getSelectedProject()
    const effectiveProjectId = input.projectId || selected.project_id || LocalWorkspace.listProjects()[0]?.id || ''
    const localFile = input.mediaFileId ? LocalWorkspace.getFileById(input.mediaFileId) : null
    const fileName = localFile?.name || input.mediaPath.split('/').pop() || input.mediaPath
    const settings = `Transl: ${input.translationProvider || 'm2m100'} / Subs: ${input.subtitlesMode || 'bilingual'} / Voice: ${input.voiceChoice || 'male'}`

    const payload = await requestJson<MediaSubmissionPayload>('/api/submit-media', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        mediaPath: input.mediaPath,
        durationSec: input.durationSec,
        sizeBytes: input.sizeBytes,
        translationProvider: input.translationProvider,
        subtitlesMode: input.subtitlesMode,
        voiceChoice: input.voiceChoice,
        forceFullReprocess: input.forceFullReprocess,
      }),
    })
    const jobId = String(payload?.result?.job_id || '').trim()
    if (jobId) {
      this.pendingJobs.set(jobId, {
        projectId: effectiveProjectId,
        mediaFileId: input.mediaFileId,
        mediaPath: input.mediaPath,
        sizeBytes: input.sizeBytes,
        durationSec: input.durationSec,
        settings,
        fileName,
      })
    }
    const immediateDocId = String(payload?.result?.document_id || '').trim()
    if (immediateDocId) {
      await this.finalizeCompletedAnalysis(immediateDocId, {
        projectId: effectiveProjectId,
        mediaFileId: input.mediaFileId,
        mediaPath: input.mediaPath,
        sizeBytes: input.sizeBytes,
        durationSec: input.durationSec,
        settings,
        fileName,
      })
    }
    return payload
  }

  async getTranslationConfig(): Promise<TranslationConfig> {
    return LocalWorkspace.getTranslationConfig() as TranslationConfig
  }

  async saveTranslationConfig(config: TranslationConfig): Promise<TranslationConfig> {
    return LocalWorkspace.saveTranslationConfig(config)
  }

  async listFiles(projectId?: string): Promise<MediaFileRow[]> {
    return LocalWorkspace.listFiles(projectId)
  }

  async listAnalysisHistory(projectId?: string): Promise<AnalysisHistoryRow[]> {
    return LocalWorkspace.listAnalysisHistory(projectId)
  }

  async listDocumentArtifacts(documentId: string): Promise<DocumentArtifact[]> {
    const docId = String(documentId || '').trim()
    if (!docId) return []
    return LocalWorkspace.listDocumentArtifacts(docId)
  }

  async getBackendJobStatus(jobId: string): Promise<BackendJobStatus> {
    const status = await requestJson<BackendJobStatus>(`/api/backend-job-status?job_id=${encodeURIComponent(jobId)}`)
    const docId = String(status.document_id || '').trim()
    if (docId && (status.status === 'completed_local' || status.status === 'running_local')) {
      const context = this.pendingJobs.get(jobId)
      if (context) {
        const finalized = await this.finalizeCompletedAnalysis(docId, context, {
          retries: status.status === 'completed_local' ? 4 : 1,
          retryDelayMs: 180,
        })
        if (status.status === 'completed_local' && finalized) this.pendingJobs.delete(jobId)
      }
    } else if (status.status === 'rejected' || status.status === 'error' || status.status === 'not_found') {
      this.pendingJobs.delete(jobId)
    }
    return status
  }

  async getVisualizerPayload(documentId?: string): Promise<VisualizerPayload> {
    if (!documentId) return {}
    const local = LocalWorkspace.getVisualizerPayload(documentId)
    if (Object.keys(local).length > 0) return local
    return requestJson<VisualizerPayload>(`/api/visualizer-payload?document_id=${encodeURIComponent(documentId)}`)
  }

  async analyzeText(input: { rawText: string; sentences?: string[] }): Promise<AnalyzeTextPayload> {
    return requestJson<AnalyzeTextPayload>('/api/analyze-text', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    })
  }

  async applyEdit(input: {
    sentenceText: string
    nodeId: string
    fieldPath: string
    newValue: string
    documentId?: string
  }): Promise<{ status: 'ok' | 'error'; message: string }> {
    const documentId = String(input.documentId || '').trim()
    if (!documentId) return { status: 'error', message: 'documentId is required.' }
    const value = input.newValue === '__NULL__' ? null : input.newValue
    return LocalWorkspace.applyEdit({
      documentId,
      sentenceText: input.sentenceText,
      nodeId: input.nodeId,
      fieldPath: input.fieldPath,
      newValue: value,
    })
  }

  async deleteAnalysis(documentId: string): Promise<{ status: 'ok' | 'error'; message: string; document_id?: string }> {
    return LocalWorkspace.deleteAnalysis(documentId)
  }

  private async finalizeCompletedAnalysis(
    documentId: string,
    context: {
      projectId: string
      mediaFileId?: string
      mediaPath: string
      sizeBytes?: number
      durationSec?: number
      settings: string
      fileName: string
    },
    options?: {
      retries?: number
      retryDelayMs?: number
    },
  ): Promise<boolean> {
    if (this.finalizedDocuments.has(documentId)) return true
    const retries = Math.max(1, Number(options?.retries || 1))
    const retryDelayMs = Math.max(0, Number(options?.retryDelayMs || 0))
    let contract: VisualizerPayload = {}
    for (let attempt = 1; attempt <= retries; attempt += 1) {
      contract = await requestJson<VisualizerPayload>(
        `/api/visualizer-payload?document_id=${encodeURIComponent(documentId)}`,
      ).catch(() => ({}))
      if (Object.keys(contract).length > 0) break
      if (attempt < retries && retryDelayMs > 0) {
        await new Promise<void>((resolve) => {
          window.setTimeout(resolve, retryDelayMs)
        })
      }
    }
    if (Object.keys(contract).length === 0) return false
    const artifacts = await requestJson<DocumentArtifact[]>(
      `/api/document-artifacts?document_id=${encodeURIComponent(documentId)}`,
    ).catch(() => [])
    LocalWorkspace.upsertAnalysis({
      documentId,
      projectId: context.projectId,
      mediaFileId: context.mediaFileId,
      fileName: context.fileName,
      filePath: context.mediaPath,
      sizeBytes: context.sizeBytes,
      durationSeconds: context.durationSec,
      settings: context.settings,
      contract,
      artifacts,
    })
    this.finalizedDocuments.add(documentId)
    return true
  }
}
