import type {
  AnalysisHistoryRow,
  AnalyzeTextPayload,
  BackendJobStatus,
  DocumentArtifact,
  MediaFileRow,
  MediaProgressPayload,
  MediaSubmissionPayload,
  ProjectRow,
  RuntimeApi,
  RuntimeUiState,
  SelectedProject,
  TranslationConfig,
  VisualizerPayload,
} from './runtimeApi'
import { LocalWorkspace } from '../lib/localWorkspace'
import { recordRuntimeDiagnostic } from '../lib/runtimeDiagnostics'
import { resolveClientMode } from '../lib/clientMode'
import {
  apiUrl,
  blobToDataUrl,
  fetchWithRetry,
  normalizeBlobLike,
  requestBlob,
  requestJson,
  shouldRetryBackendRequest,
  sleepMs,
} from '../lib/apiUtils'
import {
  buildMediaSentenceRows,
  buildSrt,
  bytesOfText,
  encodeTextArtifact,
  extractMediaSentencesFromArtifacts,
  extractRawTextFromBlob,
  inferSourceKind,
  normalizeContractError,
  normalizeText,
  replaceTextArtifact,
  simpleHash,
  splitIntoSentences,
  stripSubtitleMarkup,
} from '../lib/mediaArtifacts'
import type { ArtifactSentenceRow, TimedSentenceRow } from '../lib/mediaArtifacts'

type SentenceContractPayload = {
  sentence_text?: string
  sentence_hash?: string
  sentence_node?: VisualizerPayload[string]
}

function formatVoiceSetting(voiceChoice: string | undefined): string {
  const value = String(voiceChoice || '').trim().toLowerCase()
  if (value === 'backend_dmitry' || value === 'client_dmitry') return 'dmitry'
  if (value === 'backend_svetlana' || value === 'client_svetlana') return 'svetlana'
  return 'male'
}

export class HttpRuntimeApi implements RuntimeApi {
  async getUiState(): Promise<RuntimeUiState> {
    return requestJson<RuntimeUiState>('/api/ui-state')
  }

  async listProjects(): Promise<ProjectRow[]> {
    return await LocalWorkspace.listProjects()
  }

  async createProject(name: string): Promise<ProjectRow> {
    try {
      recordRuntimeDiagnostic('api.project', 'create.start', { name })
      const row = await LocalWorkspace.createProject(name)
      recordRuntimeDiagnostic('api.project', 'create.success', row)
      return row
    } catch (error) {
      recordRuntimeDiagnostic('api.project', 'create.error', error, 'error')
      throw error
    }
  }

  async deleteProject(projectId: string): Promise<{ status: 'ok' | 'error'; message: string; project_id?: string }> {
    try {
      recordRuntimeDiagnostic('api.project', 'delete.start', { projectId })
      const result = await LocalWorkspace.deleteProject(projectId)
      recordRuntimeDiagnostic('api.project', 'delete.success', result)
      return result
    } catch (error) {
      recordRuntimeDiagnostic('api.project', 'delete.error', error, 'error')
      throw error
    }
  }

  async getSelectedProject(): Promise<SelectedProject> {
    return await LocalWorkspace.getSelectedProject()
  }

  async setSelectedProject(projectId: string): Promise<SelectedProject> {
    return await LocalWorkspace.setSelectedProject(projectId)
  }

  async uploadMedia(file: File): Promise<{ fileName: string; mediaPath: string; sizeBytes: number }> {
    try {
      recordRuntimeDiagnostic('api.file', 'upload.start', { name: file.name, size: file.size, type: file.type })
      const fileName = String(file.name || 'uploaded.bin')
      const localId = typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
        ? crypto.randomUUID()
        : `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
      const mediaPath = `/client-media/${localId}/${fileName}`
      const uploaded = { fileName, mediaPath, sizeBytes: file.size }
      await LocalWorkspace.cacheUploadedMedia(uploaded.mediaPath, file)
      recordRuntimeDiagnostic('api.file', 'upload.success', uploaded)
      return uploaded
    } catch (error) {
      recordRuntimeDiagnostic('api.file', 'upload.error', error, 'error')
      throw error
    }
  }

  async registerMediaFile(input: {
    projectId: string
    name: string
    mediaPath: string
    sizeBytes: number
    durationSec?: number
  }): Promise<{ id: string; project_id: string; name: string; path: string; size_bytes?: number; duration_seconds?: number }> {
    try {
      recordRuntimeDiagnostic('api.file', 'register.start', input)
      const row = await LocalWorkspace.registerMediaFile(input)
      const result = {
        id: row.id,
        project_id: row.project_id,
        name: row.name,
        path: row.path || row.media_path,
        size_bytes: row.size_bytes,
        duration_seconds: row.duration_seconds,
      }
      recordRuntimeDiagnostic('api.file', 'register.success', result)
      return result
    } catch (error) {
      recordRuntimeDiagnostic('api.file', 'register.error', error, 'error')
      throw error
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
    onProgress?: (payload: MediaProgressPayload) => void
    signal?: AbortSignal
  }): Promise<MediaSubmissionPayload> {
    recordRuntimeDiagnostic('api.media', 'submit.start', {
      mediaPath: input.mediaPath,
      clientMode: resolveClientMode(),
      translationProvider: input.translationProvider,
      subtitlesMode: input.subtitlesMode,
      voiceChoice: input.voiceChoice,
      forceFullReprocess: input.forceFullReprocess,
    })
    const selected = await LocalWorkspace.getSelectedProject()
    const projects = await LocalWorkspace.listProjects()
    const effectiveProjectId = input.projectId || selected.project_id || projects[0]?.id || ''
    if (!effectiveProjectId) {
      recordRuntimeDiagnostic('api.media', 'submit.reject', 'Select project first.', 'error')
      return {
        result: {
          route: 'reject',
          status: 'rejected',
          message: 'Select project first.',
          stage_name: 'loading_file',
        },
        ui_feedback: {
          severity: 'error',
          title: 'Project is required',
          message: 'Select a project before starting pipeline.',
        },
      }
    }
    const localFile = input.mediaFileId ? await LocalWorkspace.getFileById(input.mediaFileId) : null
    const fileName = localFile?.name || input.mediaPath.split('/').pop() || input.mediaPath
    const settings = `Transl: ${input.translationProvider || 'm2m100'} / Subs: ${input.subtitlesMode || 'bilingual'} / Voice: ${formatVoiceSetting(input.voiceChoice)} / Proc: ${input.forceFullReprocess ? 'force' : 'incremental'}`
    const startedAt = Date.now()
    const stageLogs: string[] = []
    const progress: number[] = [0, 0, 0, 0, 0]
    const stageNames = ['loading_file', 'transcribing_audio', 'linguistic_parsing', 'generating_media', 'exporting_files']
    let lastLoggedText = ''
    let mediaStageClosed = false
    const ensureNotAborted = (): void => {
      if (input.signal?.aborted) {
        throw new DOMException('Analysis cancelled.', 'AbortError')
      }
    }
    const log = (stage: number, text: string, pct: number): void => {
      if (input.signal?.aborted) return
      if (stage >= 4 && !mediaStageClosed) {
        progress[3] = 100
        mediaStageClosed = true
      }
      progress[stage] = Math.max(progress[stage], Math.max(0, Math.min(100, Math.round(pct))))
      if (text !== lastLoggedText) {
        stageLogs.push(text)
        lastLoggedText = text
      }
      input.onProgress?.({
        stage_name: stageNames[stage] || '',
        message: text,
        stage_logs: stageLogs.slice(-30),
        stage_progress: [...progress],
      })
    }

    const finish = (payload: MediaSubmissionPayload): MediaSubmissionPayload => ({
      ...payload,
      result: {
        ...payload.result,
        stage_logs: stageLogs.slice(-30),
        stage_log: stageLogs.slice(-10).join('\n'),
        stage_progress: [...progress],
        processing_duration_ms: Math.max(0, Date.now() - startedAt),
      },
    })

    const mediaBlob = await LocalWorkspace.getCachedUploadedMedia(input.mediaPath)
    if (!(mediaBlob instanceof Blob)) {
      const detail = `Client media blob not found in local DB for: ${input.mediaPath}`
      recordRuntimeDiagnostic('api.media', 'submit.reject', detail, 'error')
      return finish({
        result: {
          route: 'reject',
          status: 'rejected',
          message: detail,
        },
        ui_feedback: {
          severity: 'error',
          title: 'Processing failed',
          message: `${detail}. Re-upload this file in Files and retry.`,
        },
      })
    }

    const clientMode = resolveClientMode()
    if (clientMode === 'pwa') {
      recordRuntimeDiagnostic('api.media', 'submit.backend_path', { voiceChoice: input.voiceChoice, clientMode })
      const { submitMediaPwa } = await import('../runtime/pwaMediaFlow')
      return await submitMediaPwa({
        ...input,
        projectId: effectiveProjectId,
        mediaBlob,
        fileName,
        settings,
      })
    }
    recordRuntimeDiagnostic('api.media', 'submit.desktop_path', { voiceChoice: input.voiceChoice, clientMode })
    const { submitMediaDesktop } = await import('../runtime/desktopMediaFlow')
    return await submitMediaDesktop({
      ...input,
      projectId: effectiveProjectId,
      fileName,
      settings,
    })
  }

  private async submitMediaViaBackend(input: {
    mediaPath: string
    mediaBlob: Blob
    durationSec: number
    sizeBytes: number
    projectId: string
    mediaFileId?: string
    translationProvider?: string
    subtitlesMode?: string
    voiceChoice?: string
    forceFullReprocess?: boolean
    onProgress?: (payload: MediaProgressPayload) => void
    signal?: AbortSignal
    fileName: string
    settings: string
  }): Promise<MediaSubmissionPayload> {
    const startedAt = Date.now()
    const stageLogs: string[] = []
    const progress: number[] = [0, 0, 0, 0, 0]
    const stageNames = ['loading_file', 'transcribing_audio', 'linguistic_parsing', 'generating_media', 'exporting_files']
    const push = (payload: MediaProgressPayload): void => {
      input.onProgress?.(payload)
    }
    const log = (stageName: string, message: string, incoming?: number[]): void => {
      const idx = stageNames.indexOf(stageName)
      if (Array.isArray(incoming) && incoming.length === 5) {
        for (let i = 0; i < 5; i += 1) progress[i] = Math.max(progress[i], Number(incoming[i] || 0))
      } else if (idx >= 0) {
        progress[idx] = Math.max(progress[idx], 5)
      }
      if (!stageLogs.length || stageLogs[stageLogs.length - 1] !== message) {
        stageLogs.push(message)
      }
      push({ stage_name: stageName, message, stage_logs: stageLogs.slice(-30), stage_progress: [...progress] })
    }
    const finish = (payload: MediaSubmissionPayload): MediaSubmissionPayload => ({
      ...payload,
      result: {
        ...payload.result,
        stage_logs: stageLogs.slice(-30),
        stage_log: stageLogs.slice(-10).join('\n'),
        stage_progress: [...progress],
        processing_duration_ms: Math.max(0, Date.now() - startedAt),
      },
    })
    const ensureNotAborted = (): void => {
      if (input.signal?.aborted) throw new DOMException('Analysis cancelled.', 'AbortError')
    }
    try {
      recordRuntimeDiagnostic('api.media.backend', 'submit.start', {
        mediaPath: input.mediaPath,
        fileName: input.fileName,
        voiceChoice: input.voiceChoice,
        translationProvider: input.translationProvider,
      })
      log('loading_file', 'Uploading media to backend for remote processing', [20, 0, 0, 0, 0])
      const form = new FormData()
      form.append('file', input.mediaBlob, input.fileName)
      const uploadRes = await fetchWithRetry('/api/upload', { method: 'POST', body: form, signal: input.signal }, { retries: 2, retryDelayMs: 1500 })
      if (!uploadRes.ok) {
        const text = await uploadRes.text()
        const message = shouldRetryBackendRequest(uploadRes.status)
          ? `Backend upload failed: service is temporarily unavailable (HTTP ${uploadRes.status}). Please retry in a few seconds.`
          : `Backend upload failed: HTTP ${uploadRes.status}: ${text}`
        throw new Error(message)
      }
      const uploaded = (await uploadRes.json()) as { mediaPath: string; sizeBytes: number; fileName: string }
      recordRuntimeDiagnostic('api.media.backend', 'upload.success', uploaded)
      log('loading_file', 'Media uploaded to backend', [100, 0, 0, 0, 0])
      ensureNotAborted()

      const remoteVoice = String(input.voiceChoice || '').trim().toLowerCase() === 'backend_svetlana' ? 'female' : 'male'
      const submit = await requestJson<MediaSubmissionPayload>('/api/submit-media', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          mediaPath: uploaded.mediaPath,
          durationSec: input.durationSec,
          sizeBytes: input.sizeBytes,
          projectId: input.projectId,
          mediaFileId: null,
          translationProvider: input.translationProvider,
          subtitlesMode: input.subtitlesMode,
          voiceChoice: remoteVoice,
          forceFullReprocess: input.forceFullReprocess,
        }),
        signal: input.signal,
      })
      const jobId = String(submit?.result?.job_id || '').trim()
      recordRuntimeDiagnostic('api.media.backend', 'job.submitted', { jobId })
      if (!jobId) {
        return finish(submit)
      }

      while (true) {
        ensureNotAborted()
        const status = await requestJson<BackendJobStatus>(`/api/backend-job-status?job_id=${encodeURIComponent(jobId)}`)
        recordRuntimeDiagnostic('api.media.backend', 'job.poll', {
          jobId,
          status: status.status,
          stage: status.stage_name,
          message: status.message,
        })
        log(String(status.stage_name || ''), String(status.message || ''), status.stage_progress)
        if (status.status === 'completed_local') {
          const documentId = String(status.document_id || '').trim()
          if (!documentId) {
            throw new Error('Backend completed without document_id.')
          }
          await this.finalizeBackendAnalysis(documentId, {
            projectId: input.projectId,
            mediaFileId: input.mediaFileId,
            mediaPath: input.mediaPath,
            sizeBytes: input.sizeBytes,
            durationSec: input.durationSec,
            settings: input.settings,
            fileName: input.fileName,
          })
          await requestJson('/api/delete-analysis', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ document_id: documentId }),
          }).catch(() => ({ status: 'error' }))
          recordRuntimeDiagnostic('api.media.backend', 'submit.success', { jobId, documentId })
          return finish({
            result: {
              route: 'local',
              status: 'completed_local',
              document_id: documentId,
              message: 'Backend media processing completed.',
              stage_name: 'completed',
            },
            ui_feedback: {
              severity: 'info',
              title: 'Remote processing completed',
              message: 'Backend media processing completed and saved locally.',
            },
          })
        }
        if (status.status === 'rejected' || status.status === 'error' || status.status === 'canceled' || status.status === 'not_found') {
          return finish({
            result: {
              route: 'reject',
              status: status.status,
              message: String(status.message || 'Backend processing failed.'),
              stage_name: String(status.stage_name || 'error'),
            },
            ui_feedback: {
              severity: status.status === 'canceled' ? 'warning' : 'error',
              title: status.status === 'canceled' ? 'Processing cancelled' : 'Processing failed',
              message: String(status.message || 'Backend processing failed.'),
            },
          })
        }
        await sleepMs(1000)
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        throw err
      }
      const message = err instanceof Error ? err.message : String(err)
      recordRuntimeDiagnostic('api.media.backend', 'submit.error', message, 'error')
      log('loading_file', message, [100, 0, 0, 0, 0])
      return finish({
        result: {
          route: 'reject',
          status: 'rejected',
          message,
          stage_name: 'loading_file',
        },
        ui_feedback: {
          severity: 'error',
          title: 'Processing failed',
          message,
        },
      })
    }
  }

  private async finalizeBackendAnalysis(
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
  ): Promise<void> {
    recordRuntimeDiagnostic('api.media.backend', 'finalize.start', { documentId, fileName: context.fileName })
    const contract = await requestJson<VisualizerPayload>(
      `/api/visualizer-payload?document_id=${encodeURIComponent(documentId)}`,
    )
    const remoteArtifacts = await requestJson<DocumentArtifact[]>(
      `/api/document-artifacts?document_id=${encodeURIComponent(documentId)}`,
    )
    const artifacts = LocalWorkspace.buildDocumentArtifacts(documentId, contract)
    const artifactMap = new Map<string, DocumentArtifact>(artifacts.map((row) => [row.name, row]))
    for (const row of remoteArtifacts) {
      const name = String(row.name || '').trim()
      const downloadUrl = String(row.download_url || '').trim()
      if (!name || !downloadUrl) continue
      const blob = await requestBlob(downloadUrl)
      if (name === 'translated_audio_ru.mp3' || name === 'translated_video_ru.mp4') {
        await LocalWorkspace.cacheAnalysisArtifactBlob(documentId, name, blob)
        continue
      }
      const encoded = await blobToDataUrl(blob)
      artifactMap.set(name, {
        name,
        size_bytes: row.size_bytes || blob.size,
        download_url: encoded,
      })
    }
    await LocalWorkspace.upsertAnalysis({
      documentId,
      projectId: context.projectId,
      mediaFileId: context.mediaFileId,
      fileName: context.fileName,
      filePath: context.mediaPath,
      sizeBytes: context.sizeBytes,
      durationSeconds: context.durationSec,
      settings: context.settings,
      contract,
      artifacts: Array.from(artifactMap.values()),
    })
    recordRuntimeDiagnostic('api.media.backend', 'finalize.success', {
      documentId,
      artifacts: artifactMap.size,
      sentences: Object.keys(contract || {}).length,
    })
  }

  async getTranslationConfig(): Promise<TranslationConfig> {
    return (await LocalWorkspace.getTranslationConfig()) as TranslationConfig
  }

  async saveTranslationConfig(config: TranslationConfig): Promise<TranslationConfig> {
    return await LocalWorkspace.saveTranslationConfig(config)
  }

  async listFiles(projectId?: string): Promise<MediaFileRow[]> {
    return await LocalWorkspace.listFiles(projectId)
  }

  async deleteFile(fileId: string): Promise<{ status: 'ok' | 'error'; message: string; file_id?: string }> {
    return await LocalWorkspace.deleteFile(fileId)
  }

  async listAnalysisHistory(projectId?: string): Promise<AnalysisHistoryRow[]> {
    return await LocalWorkspace.listAnalysisHistory(projectId)
  }

  async listDocumentArtifacts(documentId: string): Promise<DocumentArtifact[]> {
    const docId = String(documentId || '').trim()
    if (!docId) return []
    return await LocalWorkspace.listDocumentArtifacts(docId)
  }

  async getVisualizerPayload(documentId?: string): Promise<VisualizerPayload> {
    if (!documentId) return {}
    return await LocalWorkspace.getVisualizerPayload(documentId)
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
    return await LocalWorkspace.applyEdit({
      documentId,
      sentenceText: input.sentenceText,
      nodeId: input.nodeId,
      fieldPath: input.fieldPath,
      newValue: value,
    })
  }

  async deleteAnalysis(documentId: string): Promise<{ status: 'ok' | 'error'; message: string; document_id?: string }> {
    return await LocalWorkspace.deleteAnalysis(documentId)
  }
}
