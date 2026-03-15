import type {
  BackendJobStatus,
  DocumentArtifact,
  MediaProgressPayload,
  MediaSubmissionPayload,
  VisualizerPayload,
} from '../api/runtimeApi'
import { blobToDataUrl, fetchWithRetry, requestBlob, requestJson, shouldRetryBackendRequest, sleepMs } from '../lib/apiUtils'
import { LocalWorkspace } from '../lib/localWorkspace'
import { recordRuntimeDiagnostic } from '../lib/runtimeDiagnostics'

export async function submitMediaPwa(input: {
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

  const normalizedVoiceChoice = String(input.voiceChoice || 'backend_dmitry').trim().toLowerCase()
  if (normalizedVoiceChoice !== 'backend_dmitry' && normalizedVoiceChoice !== 'backend_svetlana') {
    const detail = `Unsupported voice choice for PWA media flow: ${normalizedVoiceChoice}`
    recordRuntimeDiagnostic('api.media', 'submit.reject', detail, 'error')
    return finish({
      result: {
        route: 'reject',
        status: 'rejected',
        message: detail,
        stage_name: 'loading_file',
      },
      ui_feedback: {
        severity: 'error',
        title: 'Processing failed',
        message: detail,
      },
    })
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

    const remoteVoice = normalizedVoiceChoice === 'backend_svetlana' ? 'female' : 'male'
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
    if (!jobId) return finish(submit)

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
        if (!documentId) throw new Error('Backend completed without document_id.')
        await finalizeBackendAnalysis(documentId, {
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
    if (err instanceof DOMException && err.name === 'AbortError') throw err
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

async function finalizeBackendAnalysis(
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
  const contract = await requestJson<VisualizerPayload>(`/api/visualizer-payload?document_id=${encodeURIComponent(documentId)}`)
  const remoteArtifacts = await requestJson<DocumentArtifact[]>(`/api/document-artifacts?document_id=${encodeURIComponent(documentId)}`)
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
