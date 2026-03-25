import type {
  AnalysisHistoryRow,
  AnalyzeTextPayload,
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
import { renderTranslatedMediaArtifacts } from '../lib/clientMediaRender'

type SentenceContractPayload = {
  sentence_text?: string
  sentence_hash?: string
  sentence_node?: VisualizerPayload[string]
}

type ArtifactSentenceRow = {
  sentence_idx: number
  sentence_text: string
  sentence_hash: string
  text_eng: string
  text_ru: string
  start: number
  end: number
  start_ms: number
  end_ms: number
  units: unknown[]
  units_ru: unknown[]
}

type TimedSentenceRow = {
  text: string
  start_ms: number
  end_ms: number
}

function isRemoteDeployment(): boolean {
  const host = typeof window !== 'undefined' ? window.location.hostname : ''
  return host !== 'localhost' && host !== '127.0.0.1' && !host.startsWith('192.168.')
}

function normalizedApiBaseUrl(): string {
  const raw = String(import.meta.env?.VITE_API_BASE_URL || '').trim()
  if (!raw) return ''
  return raw.replace(/\/+$/, '')
}

function apiUrl(path: string): string {
  if (/^(https?:|data:|blob:)/i.test(path)) return path
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  const base = normalizedApiBaseUrl()
  return base ? `${base}${normalizedPath}` : normalizedPath
}

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(apiUrl(url), init)
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`HTTP ${res.status}: ${text}`)
  }
  return (await res.json()) as T
}

async function requestBlob(url: string, init?: RequestInit): Promise<Blob> {
  const res = await fetch(apiUrl(url), init)
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`HTTP ${res.status}: ${text}`)
  }
  return await normalizeBlobLike(await res.blob())
}

function shouldRetryBackendRequest(status: number): boolean {
  return status === 502 || status === 503 || status === 504
}

async function sleepMs(ms: number): Promise<void> {
  await new Promise<void>((resolve) => window.setTimeout(resolve, ms))
}

async function fetchWithRetry(
  input: string,
  init: RequestInit,
  options?: { retries?: number; retryDelayMs?: number },
): Promise<Response> {
  const retries = Math.max(0, options?.retries ?? 1)
  const retryDelayMs = Math.max(0, options?.retryDelayMs ?? 1200)
  let lastError: unknown = null
  for (let attempt = 0; attempt <= retries; attempt += 1) {
    try {
      const res = await fetch(apiUrl(input), init)
      if (!shouldRetryBackendRequest(res.status) || attempt >= retries) return res
      lastError = new Error(`HTTP ${res.status}`)
    } catch (error) {
      lastError = error
      if (attempt >= retries) throw error
    }
    await sleepMs(retryDelayMs)
  }
  throw lastError instanceof Error ? lastError : new Error('Backend request failed.')
}

async function normalizeBlobLike(value: unknown): Promise<Blob> {
  if (value instanceof Blob) return value
  if (value && typeof (value as { arrayBuffer?: unknown }).arrayBuffer === 'function') {
    const blobLike = value as { arrayBuffer: () => Promise<ArrayBuffer>; type?: string }
    return new Blob([await blobLike.arrayBuffer()], { type: String(blobLike.type || '') })
  }
  return new Blob([value == null ? '' : String(value)])
}

async function blobToDataUrl(blob: Blob): Promise<string> {
  return await new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    reader.onerror = () => reject(reader.error || new Error('Failed to read blob.'))
    reader.onload = () => resolve(String(reader.result || ''))
    normalizeBlobLike(blob)
      .then((normalized) => reader.readAsDataURL(normalized))
      .catch(reject)
  })
}

function inferSourceKind(mediaPath: string, mimeType?: string): 'text' | 'audio' | 'video' | 'other' {
  const ext = String(mediaPath || '').toLowerCase()
  const mime = String(mimeType || '').toLowerCase()
  if (mime.startsWith('text/')) return 'text'
  if (mime.startsWith('audio/')) return 'audio'
  if (mime.startsWith('video/')) return 'video'
  if (ext.endsWith('.txt') || ext.endsWith('.md') || ext.endsWith('.srt') || ext.endsWith('.vtt') || ext.endsWith('.json')) return 'text'
  if (ext.endsWith('.mp3') || ext.endsWith('.wav') || ext.endsWith('.m4a') || ext.endsWith('.flac') || ext.endsWith('.ogg')) return 'audio'
  if (ext.endsWith('.mp4') || ext.endsWith('.mkv') || ext.endsWith('.mov') || ext.endsWith('.avi') || ext.endsWith('.webm')) return 'video'
  return 'other'
}

function normalizeText(raw: string): string {
  return String(raw || '')
    .replace(/\r\n/g, '\n')
    .replace(/[ \t]+/g, ' ')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

function stripSubtitleMarkup(raw: string): string {
  const lines = raw
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line.length > 0)
    .filter((line) => !/^\d+$/.test(line))
    .filter((line) => !/^\d{2}:\d{2}:\d{2}[,.]\d{3}\s+-->\s+\d{2}:\d{2}:\d{2}[,.]\d{3}/.test(line))
    .filter((line) => line.toUpperCase() !== 'WEBVTT')
  return lines.join(' ')
}

function splitIntoSentences(rawText: string): string[] {
  return normalizeText(rawText)
    .split(/(?<=[.!?])\s+/)
    .map((s) => s.trim())
    .filter(Boolean)
}

function normalizeContractError(errorMessage: string): string {
  const text = String(errorMessage || '').trim().toLowerCase()
  if (!text) return 'Project service is unavailable. Check internet access and service URL.'
  if (text.includes('failed to fetch') || text.includes('networkerror') || text.includes('http 404') || text.includes('http 502') || text.includes('http 503') || text.includes('http 504')) {
    return 'Project service is unavailable. Check internet access and service URL.'
  }
  return 'Project service is unavailable. Check internet access and service URL.'
}

function formatVoiceSetting(voiceChoice: string | undefined): string {
  const value = String(voiceChoice || '').trim().toLowerCase()
  if (value === 'backend_dmitry') return 'dmitry'
  if (value === 'backend_svetlana') return 'svetlana'
  return 'male'
}

function bytesOfText(text: string): number {
  return new TextEncoder().encode(text).length
}

function encodeTextArtifact(mime: string, text: string): string {
  return `data:${mime};charset=utf-8,${encodeURIComponent(text)}`
}

function simpleHash(input: string): string {
  let h = 2166136261
  for (let i = 0; i < input.length; i += 1) {
    h ^= input.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return `h${(h >>> 0).toString(16)}`
}

function formatSrtTime(ms: number): string {
  const safe = Math.max(0, Math.floor(ms))
  const hours = Math.floor(safe / 3600000)
  const minutes = Math.floor((safe % 3600000) / 60000)
  const seconds = Math.floor((safe % 60000) / 1000)
  const millis = safe % 1000
  const pad = (value: number, len: number): string => String(value).padStart(len, '0')
  return `${pad(hours, 2)}:${pad(minutes, 2)}:${pad(seconds, 2)},${pad(millis, 3)}`
}

function buildSrt(rows: ArtifactSentenceRow[], bilingual: boolean): string {
  const blocks = rows
    .map((row, idx) => {
      const lines = bilingual
        ? [String(row.text_eng || '').trim(), String(row.text_ru || '').trim()].filter(Boolean)
        : [String(row.text_eng || '').trim()].filter(Boolean)
      if (lines.length === 0) return ''
      return [
        String(idx + 1),
        `${formatSrtTime(row.start_ms)} --> ${formatSrtTime(Math.max(row.end_ms, row.start_ms + 800))}`,
        ...lines,
        '',
      ].join('\n')
    })
    .filter(Boolean)
  return blocks.join('\n')
}

function buildMediaSentenceRows(
  sentences: string[],
  translatedSentences: string[],
  timedSentences?: TimedSentenceRow[],
): ArtifactSentenceRow[] {
  return sentences.map((sentence, idx) => {
    const timed = timedSentences?.[idx]
    const startMs = typeof timed?.start_ms === 'number' ? Math.max(0, timed.start_ms) : idx * 3000
    const endMs = typeof timed?.end_ms === 'number' ? Math.max(startMs + 300, timed.end_ms) : startMs + 2600
    return {
      sentence_idx: idx,
      sentence_text: sentence,
      sentence_hash: simpleHash(`${idx}:${sentence}`),
      text_eng: sentence,
      text_ru: String(translatedSentences[idx] || '').trim(),
      start: startMs / 1000,
      end: endMs / 1000,
      start_ms: startMs,
      end_ms: endMs,
      units: [],
      units_ru: [],
    }
  })
}

function extractMediaSentencesFromArtifacts(artifacts: DocumentArtifact[]): ArtifactSentenceRow[] {
  const mediaContract = artifacts.find((row) => row.name === 'media_contract.json')
  if (!mediaContract?.download_url?.startsWith('data:')) return []
  try {
    const payload = decodeURIComponent(String(mediaContract.download_url).split(',', 2)[1] || '')
    const parsed = JSON.parse(payload) as { media_sentences?: unknown[] }
    if (!Array.isArray(parsed.media_sentences)) return []
    return parsed.media_sentences.map((row, idx) => {
      const item = (row || {}) as Record<string, unknown>
      return {
        sentence_idx: Number(item.sentence_idx ?? idx),
        sentence_text: String(item.sentence_text || item.text_eng || ''),
        sentence_hash: String(item.sentence_hash || simpleHash(`${idx}:${String(item.sentence_text || item.text_eng || '')}`)),
        text_eng: String(item.text_eng || item.sentence_text || ''),
        text_ru: String(item.text_ru || ''),
        start: Number(item.start || 0),
        end: Number(item.end || 0),
        start_ms: Number(item.start_ms || 0),
        end_ms: Number(item.end_ms || 0),
        units: Array.isArray(item.units) ? item.units : [],
        units_ru: Array.isArray(item.units_ru) ? item.units_ru : [],
      }
    })
  } catch {
    return []
  }
}

function replaceTextArtifact(artifacts: DocumentArtifact[], name: string, mime: string, text: string): void {
  const content = String(text || '').trim()
  if (!content) return
  const next: DocumentArtifact = {
    name,
    size_bytes: bytesOfText(content),
    download_url: encodeTextArtifact(mime, content),
  }
  const idx = artifacts.findIndex((row) => String(row?.name || '') === name)
  if (idx >= 0) artifacts[idx] = next
  else artifacts.push(next)
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

    recordRuntimeDiagnostic('api.media', 'submit.backend_path', { voiceChoice: normalizedVoiceChoice })
    return await this.submitMediaViaBackend({
      ...input,
      projectId: effectiveProjectId,
      mediaFileId: input.mediaFileId,
      mediaBlob,
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
    // loading_file | transcribing_audio | linguistic_parsing | generating_media | client_translation | exporting_files
    const progress: number[] = [0, 0, 0, 0, 0, 0]
    const stageNames = ['loading_file', 'transcribing_audio', 'linguistic_parsing', 'generating_media', 'client_translation', 'exporting_files']
    const log = (stageName: string, message: string, incoming?: number[]): void => {
      const idx = stageNames.indexOf(stageName)
      if (Array.isArray(incoming)) {
        for (let i = 0; i < incoming.length && i < progress.length; i += 1) {
          progress[i] = Math.max(progress[i], Number(incoming[i] || 0))
        }
      } else if (idx >= 0) {
        progress[idx] = Math.max(progress[idx], 5)
      }
      if (!stageLogs.length || stageLogs[stageLogs.length - 1] !== message) stageLogs.push(message)
      input.onProgress?.({ stage_name: stageName, message, stage_logs: stageLogs.slice(-30), stage_progress: [...progress] })
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

    type StoredSentence = { text: string; start_sec: number | null; end_sec: number | null }
    type PipelineSettings = { translationProvider: string; voiceChoice: string; subtitlesMode: string; sourceType: string }

    const runConcurrent = (tasks: Array<() => Promise<void>>, concurrency: number): Promise<void> => {
      let idx = 0
      let active = 0
      return new Promise<void>((resolve, reject) => {
        const next = (): void => {
          if (idx === tasks.length && active === 0) { resolve(); return }
          while (active < concurrency && idx < tasks.length) {
            active++
            const task = tasks[idx++]
            task().then(() => { active--; next() }).catch(reject)
          }
        }
        next()
      })
    }

    try {
      recordRuntimeDiagnostic('api.media.backend', 'submit.start', { mediaPath: input.mediaPath, fileName: input.fileName })

      // ── Resume detection ──────────────────────────────────────────
      // resumePoint: 'full' = run everything; 'translation' = reuse transcription+contracts;
      //              'tts' = reuse transcription+contracts+translations; 'done' = early exit
      let resumePoint: 'full' | 'translation' | 'tts' | 'done' = 'full'
      let documentId =
        typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
          ? crypto.randomUUID()
          : `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
      let resumeSentences: StoredSentence[] | null = null
      let resumeContract: VisualizerPayload | null = null
      let resumeTranslations: Record<string, string> | null = null
      let resumeSourceType: string | null = null

      if (!input.forceFullReprocess && input.mediaFileId) {
        const history = await LocalWorkspace.listAnalysisHistory(input.projectId)
        const existing = history
          .filter((r) => r.media_file_id === input.mediaFileId)
          .sort((a, b) => String(b.updated_at).localeCompare(String(a.updated_at)))[0]

        if (existing) {
          const [sentBlob, settBlob] = await Promise.all([
            LocalWorkspace.getAnalysisArtifactBlob(existing.document_id, 'sentences.json'),
            LocalWorkspace.getAnalysisArtifactBlob(existing.document_id, 'pipeline_settings.json'),
          ])

          if (sentBlob) {
            const prevSentences = JSON.parse(await sentBlob.text()) as StoredSentence[]

            // pipeline_settings.json only exists after a fully successful run
            const prevSettings: PipelineSettings | null = settBlob
              ? JSON.parse(await settBlob.text()) as PipelineSettings
              : null

            const currentProvider = input.translationProvider || 'm2m100'
            const currentVoice = String(input.voiceChoice || 'backend_dmitry').trim().toLowerCase()
            const currentSubs = input.subtitlesMode || 'bilingual'

            const sameProvider = prevSettings?.translationProvider === currentProvider
            const sameVoice = prevSettings?.voiceChoice === currentVoice
            const sameSubs = prevSettings?.subtitlesMode === currentSubs

            if (prevSettings && sameProvider && sameVoice && sameSubs && existing.contract_current !== false) {
              resumePoint = 'done'
              documentId = existing.document_id
            } else if (prevSentences.length > 0) {
              const rawAnalysis = await LocalWorkspace.getRawAnalysis(existing.document_id)
              if (rawAnalysis && Object.keys(rawAnalysis.contract).length > 0) {
                documentId = existing.document_id
                resumeSentences = prevSentences
                resumeContract = rawAnalysis.contract
                resumeSourceType = prevSettings?.sourceType ?? null

                if (prevSettings && sameProvider) {
                  // Extract stored translations from contract nodes
                  const translations: Record<string, string> = {}
                  for (const [key, node] of Object.entries(rawAnalysis.contract)) {
                    const active = String(node.active_translation_provider || '')
                    const t = active
                      ? (node.translations as Record<string, { text?: string }> | undefined)?.[active]?.text
                      : undefined
                    if (t) translations[key] = t
                  }
                  if (Object.keys(translations).length > 0) {
                    resumeTranslations = translations
                    resumePoint = 'tts'
                  } else {
                    resumePoint = 'translation'
                  }
                } else {
                  resumePoint = 'translation'
                }
              }
            }
          }
        }
      }

      if (resumePoint === 'done') {
        log('loading_file', 'Already analyzed — returning existing result', [100, 100, 100, 100, 100, 100])
        return finish({
          result: { route: 'local', status: 'completed_local', document_id: documentId, message: 'Analysis already completed.', stage_name: 'completed' },
          ui_feedback: { severity: 'info', title: 'Already analyzed', message: 'This file has already been analyzed.' },
        })
      }

      // ── Stage 0: Upload ──────────────────────────────────────────
      // Only needed for desktop (local) transcription path. Remote deployments
      // use client-side Whisper and per-sentence TTS — no server media path required.
      const needsUpload = resumePoint === 'full' && !isRemoteDeployment()
      let uploadedMediaPath = ''
      if (needsUpload) {
        log('loading_file', 'Uploading media to backend...', [20, 0, 0, 0, 0, 0])
        const form = new FormData()
        form.append('file', input.mediaBlob, input.fileName)
        const uploadRes = await fetchWithRetry('/api/upload', { method: 'POST', body: form, signal: input.signal }, { retries: 2, retryDelayMs: 1500 })
        if (!uploadRes.ok) {
          const text = await uploadRes.text()
          throw new Error(
            shouldRetryBackendRequest(uploadRes.status)
              ? `Backend upload failed: service temporarily unavailable (HTTP ${uploadRes.status}). Retry in a few seconds.`
              : `Backend upload failed: HTTP ${uploadRes.status}: ${text}`,
          )
        }
        const uploaded = (await uploadRes.json()) as { mediaPath: string; sizeBytes: number; fileName: string }
        uploadedMediaPath = uploaded.mediaPath
        log('loading_file', 'Media uploaded', [100, 0, 0, 0, 0, 0])
        ensureNotAborted()
      } else {
        log('loading_file', 'Ready', [100, 0, 0, 0, 0, 0])
      }

      // ── Stage 1: Transcribe ──────────────────────────────────────
      let sentences: StoredSentence[]
      let sourceType: string
      let contract: VisualizerPayload

      if (resumePoint === 'full') {
        log('transcribing_audio', 'Transcribing audio (this may take a minute)...', [100, 5, 0, 0, 0, 0])
        const transcribeResult = isRemoteDeployment()
          ? await this.clientTranscribeAudio(
              input.mediaBlob,
              input.fileName,
              (msg) => log('transcribing_audio', msg, [100, 50, 0, 0, 0, 0]),
              input.signal,
            ).then((r) => ({ ...r, full_text: r.sentences.map((s) => s.text).join(' ') }))
          : await new Promise<{ source_type: string; full_text: string; sentences: StoredSentence[] }>(
          (resolve, reject) => {
            const onAbort = (): void => reject(new DOMException('Analysis cancelled.', 'AbortError'))
            input.signal?.addEventListener('abort', onAbort)
            fetch(apiUrl('/api/transcribe'), {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ mediaPath: uploadedMediaPath }),
              signal: input.signal,
            }).then((res) => {
              if (!res.ok || !res.body) { reject(new Error(`Transcribe request failed: HTTP ${res.status}`)); return }
              const reader = res.body.getReader()
              const decoder = new TextDecoder()
              let buf = ''
              const pump = (): void => {
                reader.read().then(({ done, value }) => {
                  if (done) { reject(new Error('Transcribe stream ended without done event')); return }
                  buf += decoder.decode(value, { stream: true })
                  const parts = buf.split('\n\n')
                  buf = parts.pop() ?? ''
                  for (const part of parts) {
                    const dataLine = part.split('\n').find((l) => l.startsWith('data: '))
                    if (!dataLine) continue
                    try {
                      const evt = JSON.parse(dataLine.slice(6)) as { status: string; source_type?: string; full_text?: string; sentences?: StoredSentence[]; error?: string }
                      if (evt.status === 'done') {
                        input.signal?.removeEventListener('abort', onAbort)
                        resolve({ source_type: evt.source_type ?? 'audio', full_text: evt.full_text ?? '', sentences: evt.sentences ?? [] })
                        return
                      }
                      if (evt.status === 'error') {
                        input.signal?.removeEventListener('abort', onAbort)
                        reject(new Error(`Transcription failed: ${evt.error || 'unknown'}`))
                        return
                      }
                    } catch { /* malformed SSE line */ }
                  }
                  pump()
                }).catch(reject)
              }
              pump()
            }).catch(reject)
          },
        )
        sentences = transcribeResult.sentences || []
        sourceType = String(transcribeResult.source_type || 'audio').trim()
        log('transcribing_audio', `Transcribed ${sentences.length} sentences`, [100, 100, 0, 0, 0, 0])
        ensureNotAborted()

        // Persist sentences for future resume (pipeline_settings saved only on full success)
        await LocalWorkspace.cacheAnalysisArtifactBlob(
          documentId,
          'sentences.json',
          new Blob([JSON.stringify(sentences)], { type: 'application/json' }),
        )
      } else {
        sentences = resumeSentences!
        sourceType = resumeSourceType ?? 'audio'
        log('transcribing_audio', 'Reusing existing transcription', [100, 100, 0, 0, 0, 0])
      }

      // ── Stage 2: Sentence contracts ──────────────────────────────
      if (resumePoint === 'full') {
        contract = {}
        const total = sentences.length
        let contractsDone = 0
        log('linguistic_parsing', `Building sentence contracts (0/${total})...`, [100, 100, 5, 0, 0, 0])
        await runConcurrent(
          sentences.map((sent, i) => async () => {
            ensureNotAborted()
            try {
              const result = await requestJson<SentenceContractPayload>('/api/sentence-contract', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ sentenceText: sent.text, sentenceIdx: i }),
                signal: input.signal,
              })
              if (result.sentence_node && sent.text) contract[sent.text] = result.sentence_node
            } catch (err) {
              recordRuntimeDiagnostic('api.media.backend', 'sentence-contract.error', String(err instanceof Error ? err.message : err), 'error')
            }
            contractsDone++
            log('linguistic_parsing', `Processing sentences (${contractsDone}/${total})`, [100, 100, Math.round((contractsDone / Math.max(total, 1)) * 100), 0, 0, 0])
          }),
          3,
        )
        log('linguistic_parsing', `Contracts built (${Object.keys(contract).length}/${total})`, [100, 100, 100, 100, 0, 0])
        ensureNotAborted()

        // Intermediate save — contractCurrent: false keeps file.analyzed = false until pipeline completes
        await LocalWorkspace.upsertAnalysis({
          documentId,
          projectId: input.projectId,
          mediaFileId: input.mediaFileId,
          fileName: input.fileName,
          filePath: input.mediaPath,
          sizeBytes: input.sizeBytes,
          durationSeconds: input.durationSec,
          settings: input.settings,
          contract,
          artifacts: LocalWorkspace.buildDocumentArtifacts(documentId, contract),
          contractCurrent: false,
        })
      } else {
        contract = resumeContract!
        progress[2] = 100
        progress[3] = 100
        log('linguistic_parsing', 'Reusing existing contracts', [100, 100, 100, 100, 0, 0])
      }

      // ── Stage 3: Translation ─────────────────────────────────────
      let translations: Record<string, string> = {}
      if (resumePoint === 'tts' && resumeTranslations) {
        translations = resumeTranslations
        progress[4] = 100
        log('client_translation', 'Reusing existing translations', [100, 100, 100, 100, 100, 0])
      } else {
        const sentenceKeys = Object.keys(contract)
        if (sentenceKeys.length > 0) {
          log('client_translation', `Translating sentences (0/${sentenceKeys.length})...`, [100, 100, 100, 100, 5, 0])
          translations = await this.clientTranslateAnalysis(
            documentId,
            contract,
            (done, ttl) => {
              progress[4] = Math.round((done / Math.max(ttl, 1)) * 100)
              log('client_translation', `Translating sentences (${done}/${ttl})`, [...progress])
            },
            input.signal,
          ).catch((err: unknown) => {
            recordRuntimeDiagnostic('api.media.backend', 'translate.error', String(err instanceof Error ? err.message : err), 'error')
            return {}
          })
        }
        progress[4] = 100
        log('client_translation', 'Translation complete', [...progress])
      }
      ensureNotAborted()

      // ── Stage 4: Per-sentence TTS + client render ─────────────────
      if (sourceType === 'audio' || sourceType === 'video') {
        log('exporting_files', 'Generating translated audio...', [100, 100, 100, 100, 100, 5])
        const voiceForCache = String(input.voiceChoice || '').trim().toLowerCase() === 'backend_svetlana' ? 'female' : 'male'
        const timedSentences = sentences.map((sent) => ({
          text_eng: sent.text,
          text_ru: String(translations[sent.text] || ''),
          start_ms: typeof sent.start_sec === 'number' ? Math.round(sent.start_sec * 1000) : 0,
          end_ms: typeof sent.end_sec === 'number' ? Math.round(sent.end_sec * 1000) : 0,
        }))

        const ttsProvider = async (idx: number, text: string): Promise<Blob> => {
          const cacheKey = `tts_seg_${idx}_${voiceForCache}.mp3`
          const cached = await LocalWorkspace.getAnalysisArtifactBlob(documentId, cacheKey)
          if (cached) return cached
          ensureNotAborted()
          const res = await fetch(apiUrl('/api/tts-sentence'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text, voiceChoice: voiceForCache }),
            signal: input.signal,
          })
          if (!res.ok) throw new Error(`TTS sentence failed: HTTP ${res.status}`)
          const blob = await normalizeBlobLike(await res.blob())
          await LocalWorkspace.cacheAnalysisArtifactBlob(documentId, cacheKey, blob)
          return blob
        }

        try {
          const rendered = await renderTranslatedMediaArtifacts({
            sourceBlob: input.mediaBlob,
            sourceKind: sourceType as 'audio' | 'video',
            subtitlesMode: input.subtitlesMode || 'bilingual',
            voiceChoice: voiceForCache,
            sentences: timedSentences,
            onProgress: (msg, pct) => log('exporting_files', msg, [100, 100, 100, 100, 100, Math.max(5, Math.round(pct))]),
            ttsProvider,
          })

          if (!rendered) throw new Error('Media render returned null')
          ensureNotAborted()

          await LocalWorkspace.cacheAnalysisArtifactBlob(documentId, 'translated_audio_ru.mp3', rendered.translatedAudio)
          if (sourceType === 'video') {
            await LocalWorkspace.cacheAnalysisArtifactBlob(documentId, 'translated_video_ru.mp4', rendered.translatedVideo)
          }

          const artifactMap = new Map<string, DocumentArtifact>(
            LocalWorkspace.buildDocumentArtifacts(documentId, contract).map((row) => [row.name, row]),
          )
          artifactMap.set('subtitles_en.srt', { name: 'subtitles_en.srt', size_bytes: rendered.subtitlesEn.length, download_url: encodeTextArtifact('text/plain', rendered.subtitlesEn) })
          artifactMap.set('subtitles_bilingual.srt', { name: 'subtitles_bilingual.srt', size_bytes: rendered.subtitlesBilingual.length, download_url: encodeTextArtifact('text/plain', rendered.subtitlesBilingual) })
          artifactMap.set('subtitles_target.srt', { name: 'subtitles_target.srt', size_bytes: rendered.subtitlesTarget.length, download_url: encodeTextArtifact('text/plain', rendered.subtitlesTarget) })

          // Final save: contractCurrent: true → file.analyzed = true
          await LocalWorkspace.upsertAnalysis({
            documentId,
            projectId: input.projectId,
            mediaFileId: input.mediaFileId,
            fileName: input.fileName,
            filePath: input.mediaPath,
            sizeBytes: input.sizeBytes,
            durationSeconds: input.durationSec,
            settings: input.settings,
            contract,
            artifacts: Array.from(artifactMap.values()),
            contractCurrent: true,
          })

          // Persist completed settings — used by future resume detection
          await LocalWorkspace.cacheAnalysisArtifactBlob(
            documentId,
            'pipeline_settings.json',
            new Blob([JSON.stringify({
              translationProvider: input.translationProvider || 'm2m100',
              voiceChoice: String(input.voiceChoice || 'backend_dmitry').trim().toLowerCase(),
              subtitlesMode: input.subtitlesMode || 'bilingual',
              sourceType,
            } satisfies PipelineSettings)], { type: 'application/json' }),
          )

          log('exporting_files', 'Artifacts saved', [100, 100, 100, 100, 100, 100])
        } catch (renderErr) {
          if (renderErr instanceof DOMException && renderErr.name === 'AbortError') throw renderErr
          recordRuntimeDiagnostic('api.media.backend', 'render.error', String(renderErr instanceof Error ? renderErr.message : renderErr), 'error')
          log('exporting_files', 'Media render failed — analysis saved without audio', [100, 100, 100, 100, 100, 100])
        }
      } else {
        progress[5] = 100
        log('exporting_files', 'Text analysis complete', [100, 100, 100, 100, 100, 100])
      }

      recordRuntimeDiagnostic('api.media.backend', 'submit.success', { documentId, sentences: Object.keys(contract).length })
      return finish({
        result: { route: 'local', status: 'completed_local', document_id: documentId, message: 'Analysis completed.', stage_name: 'completed' },
        ui_feedback: { severity: 'info', title: 'Analysis completed', message: 'Media analysis completed and saved locally.' },
      })
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') throw err
      const message = err instanceof Error ? err.message : String(err)
      recordRuntimeDiagnostic('api.media.backend', 'submit.error', message, 'error')
      return finish({
        result: { route: 'reject', status: 'rejected', message, stage_name: 'loading_file' },
        ui_feedback: { severity: 'error', title: 'Processing failed', message },
      })
    }
  }

  private async clientTranscribeAudio(
    mediaBlob: Blob,
    fileName: string,
    onProgress: (msg: string) => void,
    signal?: AbortSignal,
  ): Promise<{ source_type: string; sentences: Array<{ text: string; start_sec: number | null; end_sec: number | null }> }> {
    const isVideo = mediaBlob.type.startsWith('video/') || /\.(mp4|mov|avi|mkv|webm)$/i.test(fileName)
    const source_type = isVideo ? 'video' : 'audio'

    // AudioContext is unavailable in Web Workers — decode here in the main thread
    // and pass a Float32Array to the worker instead of a URL.
    onProgress('Decoding audio…')
    console.log('[clientTranscribeAudio] decoding', fileName, mediaBlob.type, mediaBlob.size, 'bytes')
    const AudioCtx = (window as typeof window & { webkitAudioContext?: typeof AudioContext }).AudioContext
      ?? (window as typeof window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
    if (!AudioCtx) throw new Error('AudioContext is unavailable in this browser.')
    const audioCtx = new AudioCtx()
    const arrayBuffer = await mediaBlob.arrayBuffer()
    const audioBuffer = await audioCtx.decodeAudioData(arrayBuffer)
    await audioCtx.close().catch(() => undefined)
    // Mix down to mono
    const audio = audioBuffer.numberOfChannels > 1
      ? (() => {
          const ch0 = audioBuffer.getChannelData(0)
          const ch1 = audioBuffer.getChannelData(1)
          const mono = new Float32Array(ch0.length)
          for (let i = 0; i < ch0.length; i++) mono[i] = (ch0[i] + ch1[i]) / 2
          return mono
        })()
      : new Float32Array(audioBuffer.getChannelData(0))
    const sampling_rate = audioBuffer.sampleRate
    console.log('[clientTranscribeAudio] decoded:', audioBuffer.duration.toFixed(1), 's,', audio.length, 'samples, sr:', sampling_rate, 'channels:', audioBuffer.numberOfChannels)

    if (signal?.aborted) throw new DOMException('Analysis cancelled.', 'AbortError')

    return new Promise((resolve, reject) => {
      const worker = new Worker(new URL('../workers/whisperWorker.ts', import.meta.url), { type: 'module' })
      const id = Math.random().toString(36).slice(2)
      const onAbort = (): void => { worker.terminate(); reject(new DOMException('Analysis cancelled.', 'AbortError')) }
      signal?.addEventListener('abort', onAbort)
      worker.onmessage = (ev: MessageEvent): void => {
        const msg = ev.data as { type: string; id: string; message?: string; fullText?: string; sentences?: Array<{ text: string; start_sec: number; end_sec: number }> }
        if (msg.id !== id) return
        if (msg.type === 'progress') {
          onProgress(msg.message ?? 'Transcribing…')
        } else if (msg.type === 'done') {
          signal?.removeEventListener('abort', onAbort)
          worker.terminate()
          resolve({ source_type, sentences: msg.sentences ?? [] })
        } else if (msg.type === 'error') {
          signal?.removeEventListener('abort', onAbort)
          worker.terminate()
          reject(new Error(msg.message ?? 'Whisper worker error'))
        }
      }
      worker.onerror = (err): void => {
        signal?.removeEventListener('abort', onAbort)
        worker.terminate()
        reject(new Error(String(err.message || 'Whisper worker crashed')))
      }
      // Transfer the buffer to avoid copying (worker takes ownership)
      worker.postMessage({ type: 'transcribe', id, audio, sampling_rate }, [audio.buffer])
    })
  }

  private clientTranslateAnalysis(
    documentId: string,
    contract: VisualizerPayload,
    onProgress: (done: number, total: number, text: string) => void,
    signal?: AbortSignal,
  ): Promise<Record<string, string>> {
    return new Promise((resolve, reject) => {
      const sentences = Object.keys(contract)
      if (!sentences.length) {
        resolve({})
        return
      }
      const worker = new Worker(new URL('../workers/translationWorker.ts', import.meta.url), { type: 'module' })
      const id = documentId
      const translations: Record<string, string> = {}
      const onAbort = (): void => {
        worker.terminate()
        reject(new DOMException('Analysis cancelled.', 'AbortError'))
      }
      signal?.addEventListener('abort', onAbort)
      worker.onmessage = (ev: MessageEvent): void => {
        const msg = ev.data as { type: string; id?: string; index?: number; total?: number; text?: string; message?: string }
        if (msg.type === 'result' && msg.id === id && typeof msg.index === 'number') {
          const sentenceText = sentences[msg.index]
          if (sentenceText) translations[sentenceText] = String(msg.text || '')
          onProgress(msg.index + 1, msg.total ?? sentences.length, String(msg.text || ''))
        } else if (msg.type === 'done' && msg.id === id) {
          signal?.removeEventListener('abort', onAbort)
          worker.terminate()
          LocalWorkspace.updateAnalysisTranslations(documentId, translations).then(() => resolve(translations)).catch(reject)
        } else if (msg.type === 'error') {
          signal?.removeEventListener('abort', onAbort)
          worker.terminate()
          reject(new Error(String(msg.message || 'Translation worker error')))
        }
      }
      worker.onerror = (err): void => {
        signal?.removeEventListener('abort', onAbort)
        worker.terminate()
        reject(new Error(String(err.message || 'Translation worker crashed')))
      }
      worker.postMessage({ type: 'translate', id, sentences })
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
