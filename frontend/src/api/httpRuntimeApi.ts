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

    try {
      recordRuntimeDiagnostic('api.media.backend', 'submit.start', { mediaPath: input.mediaPath, fileName: input.fileName })

      // ── Stage 0: Upload ──────────────────────────────────────────
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
      log('loading_file', 'Media uploaded', [100, 0, 0, 0, 0, 0])
      ensureNotAborted()

      // ── Stage 1: Transcribe ──────────────────────────────────────
      log('transcribing_audio', 'Transcribing audio (this may take a minute)...', [100, 5, 0, 0, 0, 0])
      const transcribeResult = await requestJson<{
        source_type: string
        full_text: string
        sentences: Array<{ text: string; start_sec: number | null; end_sec: number | null }>
      }>('/api/transcribe', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mediaPath: uploaded.mediaPath }),
        signal: input.signal,
      })
      const sentences = transcribeResult.sentences || []
      const sourceType = String(transcribeResult.source_type || 'audio').trim()
      log('transcribing_audio', `Transcribed ${sentences.length} sentences`, [100, 100, 0, 0, 0, 0])
      ensureNotAborted()

      // ── Stage 2: Sentence contracts (parallel, concurrency = 3) ─
      const documentId =
        typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
          ? crypto.randomUUID()
          : `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
      const contract: VisualizerPayload = {}
      const total = sentences.length
      let contractsDone = 0

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
          const pct = Math.round((contractsDone / Math.max(total, 1)) * 100)
          log('linguistic_parsing', `Processing sentences (${contractsDone}/${total})`, [100, 100, pct, 0, 0, 0])
        }),
        3,
      )
      progress[3] = 100 // generating_media — skip, mark complete
      log('linguistic_parsing', `Contracts built (${Object.keys(contract).length}/${total})`, [100, 100, 100, 100, 0, 0])
      ensureNotAborted()

      // Save initial analysis (without translations or TTS artifacts)
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
      })

      // ── Stage 3: Client translation ──────────────────────────────
      let translations: Record<string, string> = {}
      const sentenceKeys = Object.keys(contract)
      if (sentenceKeys.length > 0) {
        log('client_translation', `Translating sentences (0/${sentenceKeys.length})...`, [100, 100, 100, 100, 5, 0])
        translations = await this.clientTranslateAnalysis(
          documentId,
          contract,
          (done, ttl) => {
            const pct = Math.round((done / Math.max(ttl, 1)) * 100)
            progress[4] = pct
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
      ensureNotAborted()

      // ── Stage 4: TTS batch ───────────────────────────────────────
      if (sourceType === 'audio' || sourceType === 'video') {
        log('exporting_files', 'Generating translated audio...', [100, 100, 100, 100, 100, 5])
        const timedSentences = sentences.map((sent) => ({
          text_en: sent.text,
          text_ru: String(translations[sent.text] || ''),
          start_ms: typeof sent.start_sec === 'number' ? Math.round(sent.start_sec * 1000) : 0,
          end_ms: typeof sent.end_sec === 'number' ? Math.round(sent.end_sec * 1000) : 0,
        }))
        const voiceChoice = String(input.voiceChoice || '').trim().toLowerCase() === 'backend_svetlana' ? 'female' : 'male'
        try {
          // Start async TTS job — returns immediately with job_id
          const ttsStarted = await requestJson<{ job_id: string; status: string }>('/api/tts-batch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              documentId,
              mediaPath: uploaded.mediaPath,
              sentences: timedSentences,
              voiceChoice,
              subtitlesMode: input.subtitlesMode || 'bilingual',
              sourceType,
            }),
            signal: input.signal,
          })
          const ttsJobId = String(ttsStarted.job_id || documentId)
          // Poll until TTS job completes
          let ttsArtifacts: Array<{ name: string; size_bytes: number; download_url: string }> = []
          for (;;) {
            ensureNotAborted()
            await sleepMs(2000)
            ensureNotAborted()
            const ttsStatus = await requestJson<{
              job_id: string
              status: string
              artifacts?: Array<{ name: string; size_bytes: number; download_url: string }>
              error?: string
            }>(`/api/tts-job-status?job_id=${encodeURIComponent(ttsJobId)}`)
            if (ttsStatus.status === 'done') {
              ttsArtifacts = ttsStatus.artifacts || []
              break
            }
            if (ttsStatus.status === 'error') {
              throw new Error(`TTS generation failed: ${ttsStatus.error || 'unknown error'}`)
            }
            log('exporting_files', 'Generating translated audio...', [100, 100, 100, 100, 100, 30])
          }
          log('exporting_files', 'Downloading audio artifacts...', [100, 100, 100, 100, 100, 60])
          const artifactMap = new Map<string, DocumentArtifact>(
            LocalWorkspace.buildDocumentArtifacts(documentId, contract).map((row) => [row.name, row]),
          )
          for (const row of ttsArtifacts) {
            const name = String(row.name || '').trim()
            const downloadUrl = String(row.download_url || '').trim()
            if (!name || !downloadUrl) continue
            const blob = await requestBlob(downloadUrl)
            if (name === 'translated_audio_ru.mp3' || name === 'translated_video_ru.mp4') {
              await LocalWorkspace.cacheAnalysisArtifactBlob(documentId, name, blob)
            } else {
              artifactMap.set(name, { name, size_bytes: row.size_bytes || blob.size, download_url: await blobToDataUrl(blob) })
            }
          }
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
          })
          // Cleanup server-side temp files (fire-and-forget)
          requestJson('/api/delete-analysis', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ document_id: documentId }),
          }).catch(() => {})
          log('exporting_files', 'Audio artifacts saved', [100, 100, 100, 100, 100, 100])
        } catch (ttsErr) {
          if (ttsErr instanceof DOMException && ttsErr.name === 'AbortError') throw ttsErr
          recordRuntimeDiagnostic('api.media.backend', 'tts-batch.error', String(ttsErr instanceof Error ? ttsErr.message : ttsErr), 'error')
          log('exporting_files', 'TTS failed — analysis saved without audio', [100, 100, 100, 100, 100, 100])
        }
      } else {
        progress[5] = 100
        log('exporting_files', 'Text analysis complete', [100, 100, 100, 100, 100, 100])
      }

      recordRuntimeDiagnostic('api.media.backend', 'submit.success', { documentId, sentences: Object.keys(contract).length })
      return finish({
        result: {
          route: 'local',
          status: 'completed_local',
          document_id: documentId,
          message: 'Analysis completed.',
          stage_name: 'completed',
        },
        ui_feedback: {
          severity: 'info',
          title: 'Analysis completed',
          message: 'Media analysis completed and saved locally.',
        },
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
