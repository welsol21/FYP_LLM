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

/** Parse a ZIP file (STORED entries only) into a filename→Uint8Array map. */
function parseStoredZip(buf: ArrayBuffer): Map<string, Uint8Array> {
  const view = new DataView(buf)
  const bytes = new Uint8Array(buf)
  const result = new Map<string, Uint8Array>()
  // Find End of Central Directory signature (0x06054b50)
  let eocd = buf.byteLength - 22
  while (eocd >= 0 && view.getUint32(eocd, true) !== 0x06054b50) eocd--
  if (eocd < 0) throw new Error('Invalid ZIP: EOCD not found')
  const cdOffset = view.getUint32(eocd + 16, true)
  const cdCount = view.getUint16(eocd + 8, true)
  let pos = cdOffset
  for (let i = 0; i < cdCount; i++) {
    if (view.getUint32(pos, true) !== 0x02014b50) break
    const nameLen = view.getUint16(pos + 28, true)
    const extraLen = view.getUint16(pos + 30, true)
    const commentLen = view.getUint16(pos + 32, true)
    const localOffset = view.getUint32(pos + 42, true)
    const name = new TextDecoder().decode(bytes.subarray(pos + 46, pos + 46 + nameLen))
    pos += 46 + nameLen + extraLen + commentLen
    // Read local file header to get data offset
    const lnLen = view.getUint16(localOffset + 26, true)
    const leLen = view.getUint16(localOffset + 28, true)
    const compSize = view.getUint32(localOffset + 18, true)
    const dataStart = localOffset + 30 + lnLen + leLen
    result.set(name, bytes.slice(dataStart, dataStart + compSize))
  }
  return result
}

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

const PWA_INSTALL_MESSAGE =
  'AI models are not installed. Please install the ELA app: open the browser menu and choose "Install app" / "Add to Home Screen", then reopen it.'

function isPwaModelMissingError(err: unknown): boolean {
  const msg = String(err instanceof Error ? err.message : err || '').toLowerCase()
  return (
    msg.includes('could not locate file') ||
    msg.includes('allowremotemodels') ||
    msg.includes('localmodelpath') ||
    (msg.includes('404') && (msg.includes('onnx') || msg.includes('config.json') || msg.includes('tokenizer')))
  )
}

function normalizeContractError(errorMessage: string): string {
  const text = String(errorMessage || '').trim().toLowerCase()
  if (!text) return 'Project service is unavailable. Check internet access and service URL.'
  if (text.includes('failed to fetch') || text.includes('networkerror') || text.includes('http 404') || text.includes('http 502') || text.includes('http 503') || text.includes('http 504')) {
    return 'Project service is unavailable. Check internet access and service URL.'
  }
  return 'Project service is unavailable. Check internet access and service URL.'
}

// Stage-scoped document IDs so that caching at each pipeline stage
// is invalidated only by the parameters that stage actually depends on.
//
//  immutableDocId  = hash(fileName)                          — Whisper output
//  contractDocId   = hash(fileName | translationProvider)    — contracts + translations
//  variantDocId    = hash(fileName | provider | voice | subs)— TTS audio + video + done-marker
async function computeImmutableDocId(fileName: string): Promise<string> {
  const hashBuf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(fileName))
  return Array.from(new Uint8Array(hashBuf)).map((b) => b.toString(16).padStart(2, '0')).join('')
}

async function computeContractDocId(fileName: string, translationProvider: string): Promise<string> {
  const input = `${fileName}|${translationProvider}`
  const hashBuf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(input))
  return Array.from(new Uint8Array(hashBuf)).map((b) => b.toString(16).padStart(2, '0')).join('')
}

async function computeVariantDocId(
  fileName: string,
  settings: { translationProvider: string; voiceChoice: string; subtitlesMode: string },
): Promise<string> {
  const input = `${fileName}|${settings.translationProvider}|${settings.voiceChoice}|${settings.subtitlesMode}`
  const hashBuf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(input))
  return Array.from(new Uint8Array(hashBuf)).map((b) => b.toString(16).padStart(2, '0')).join('')
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
    translatorOptions?: { id: string; credentials: Record<string, string> }[]
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
    translatorOptions?: { id: string; credentials: Record<string, string> }[]
  }): Promise<MediaSubmissionPayload> {
    const startedAt = Date.now()
    const stageLogs: string[] = []
    const progress: number[] = [0, 0, 0, 0, 0]
    const stageNames = ['loading_file', 'transcribing_audio', 'linguistic_parsing', 'generating_media', 'exporting_files']
    let mediaStageClosed = false
    const log = (stage: number, text: string, pct: number): void => {
      if (input.signal?.aborted) return  // stop progress updates once cancelled
      if (stage >= 4 && !mediaStageClosed) {
        progress[3] = 100
        mediaStageClosed = true
      }
      progress[stage] = Math.max(progress[stage], Math.max(0, Math.min(100, Math.round(pct))))
      if (!stageLogs.length || stageLogs[stageLogs.length - 1] !== text) stageLogs.push(text)
      input.onProgress?.({ stage_name: stageNames[stage] || '', message: text, stage_logs: stageLogs.slice(-30), stage_progress: [...progress] })
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
      // Three stage-scoped IDs so each stage is invalidated only by what it depends on:
      //   immutableDocId  — Whisper output (sentences.json): only file name
      //   contractDocId   — contracts + translations: file + provider
      //   documentId      — TTS audio/video + done-marker: all settings (variant)
      // resumePoint: 'full' = run everything; 'translation' = reuse transcription+contracts;
      //              'tts' = reuse transcription+contracts+translations; 'done' = early exit
      const provider = input.translationProvider || 'm2m100'
      const docIdSettings = {
        translationProvider: provider,
        voiceChoice: String(input.voiceChoice || 'backend_dmitry').trim().toLowerCase(),
        subtitlesMode: input.subtitlesMode || 'bilingual',
      }
      const immutableDocId = await computeImmutableDocId(input.fileName)
      const contractDocId = await computeContractDocId(input.fileName, provider)
      const documentId = await computeVariantDocId(input.fileName, docIdSettings)
      recordRuntimeDiagnostic('api.media.resume', 'docids', {
        fileName: input.fileName,
        provider,
        immutableDocId,
        contractDocId,
        variantDocId: documentId,
      })
      let resumePoint: 'full' | 'translation' | 'tts' | 'done' = 'full'
      let resumeSentences: StoredSentence[] | null = null
      let resumeContract: VisualizerPayload | null = null
      let resumeTranslations: Record<string, string> | null = null
      let resumeSourceType: string | null = null

      if (!input.forceFullReprocess) {
        const [sentBlob, settBlob] = await Promise.all([
          LocalWorkspace.getAnalysisArtifactBlob(immutableDocId, 'sentences.json'),
          LocalWorkspace.getAnalysisArtifactBlob(documentId, 'pipeline_settings.json'),
        ])

        recordRuntimeDiagnostic('api.media.resume', 'blobs', {
          immutableDocId,
          contractDocId,
          variantDocId: documentId,
          hasSentBlob: !!sentBlob,
          hasSettBlob: !!settBlob,
        })

        if (settBlob) {
          // pipeline_settings.json only exists after a fully successful run for this variant
          resumePoint = 'done'
        } else if (sentBlob) {
          const prevSentences = JSON.parse(await sentBlob.text()) as StoredSentence[]
          if (prevSentences.length > 0) {
            const rawAnalysis = await LocalWorkspace.getRawAnalysis(contractDocId)
            if (rawAnalysis && Object.keys(rawAnalysis.contract).length > 0) {
              resumeSentences = prevSentences
              resumeContract = rawAnalysis.contract
              resumeSourceType = (rawAnalysis as any).sourceType ?? null

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
              // sentences.json exists but contract was lost (interrupted run after Whisper, before stage 2)
              // Skip Whisper, keep resumePoint='full' so contracts are rebuilt from scratch
              resumeSentences = prevSentences
              resumeSourceType = 'audio'
              recordRuntimeDiagnostic('api.media.resume', 'no-contract', {
                contractDocId,
                hasRawAnalysis: !!rawAnalysis,
                contractKeys: rawAnalysis ? Object.keys(rawAnalysis.contract).length : 0,
                action: 'skip-whisper-rebuild-contracts',
              })
            }
          } else {
            recordRuntimeDiagnostic('api.media.resume', 'empty-sentences', { immutableDocId, sentBlobSize: sentBlob.size })
          }
        }
      }

      recordRuntimeDiagnostic('api.media.resume', 'detection', {
        resumePoint,
        mediaFileId: input.mediaFileId || null,
        forceFullReprocess: input.forceFullReprocess || false,
      })

      if (resumePoint === 'done') {
        progress.fill(100)
        log(0, 'Already analyzed — returning existing result', 100)
        return finish({
          result: { route: 'local', status: 'completed_local', document_id: documentId, message: 'Analysis already completed.', stage_name: 'completed' },
          ui_feedback: { severity: 'info', title: 'Already analyzed', message: 'This file has already been analyzed.' },
        })
      }

      // ── Stage 0: Ready ───────────────────────────────────────────
      log(0, 'Ready', 100)

      // ── Stage 1: Transcribe ──────────────────────────────────────
      let sentences: StoredSentence[]
      let sourceType: string
      let contract: VisualizerPayload

      const fileExt = input.fileName.split('.').pop()?.toLowerCase() ?? ''
      const isTextFile = ['txt', 'md', 'rtf', 'pdf', 'docx', 'doc'].includes(fileExt)

      if (resumePoint === 'full' && resumeSentences === null) {
        if (isTextFile) {
          // Text/PDF/DOCX — extract sentences via backend, no Whisper
          log(1, 'Extracting text from document…', 10)
          const extractResult = await requestJson<{ source_type: string; sentences: Array<{ text: string; start_sec: number | null; end_sec: number | null }> }>(
            apiUrl('/api/extract-text'),
            {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ mediaPath: input.mediaPath }),
              signal: input.signal,
            },
          )
          sentences = (extractResult.sentences || []).map((s) => ({ text: s.text, start_sec: s.start_sec, end_sec: s.end_sec }))
          sourceType = extractResult.source_type || 'text'
          log(1, `Extracted ${sentences.length} sentences from document`, 100)
          ensureNotAborted()
        } else {
        const durationMin = Math.round((input.durationSec ?? 0) / 60)
        const timeHint = durationMin > 2 ? ` (~${durationMin * 2}–${durationMin * 4} min on CPU)` : ''
        log(1, `Loading Whisper model…${timeHint}`, 3)
        const transcribeResult = await this.clientTranscribeAudio(
          input.mediaBlob,
          input.fileName,
          (msg, pct = 50) => log(1, msg, pct),
          input.signal,
        ).then((r) => ({ ...r, full_text: r.sentences.map((s) => s.text).join(' ') }))
        sentences = transcribeResult.sentences || []
        sourceType = String(transcribeResult.source_type || 'audio').trim()
        log(1, `Transcribed ${sentences.length} sentences`, 100)
        ensureNotAborted()
        }

        // Persist sentences under immutableDocId — independent of voice/subs/provider
        await LocalWorkspace.cacheAnalysisArtifactBlob(
          immutableDocId,
          'sentences.json',
          new Blob([JSON.stringify(sentences)], { type: 'application/json' }),
        )
        recordRuntimeDiagnostic('api.media.resume', 'sentences-saved', { immutableDocId, count: sentences.length })
      } else {
        sentences = resumeSentences!
        sourceType = resumeSourceType ?? 'audio'
        log(1, 'Reusing existing transcription', 100)
      }

      // ── Stage 2: Sentence contracts ──────────────────────────────
      if (resumePoint === 'full') {
        contract = {}
        const total = sentences.length
        let contractsDone = 0
        log(2, `Building sentence contracts (0/${total})...`, 0)
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
              if (err instanceof DOMException && err.name === 'AbortError') throw err
              recordRuntimeDiagnostic('api.media.backend', 'sentence-contract.error', String(err instanceof Error ? err.message : err), 'error')
            }
            contractsDone++
            log(2, `Processing sentences (${contractsDone}/${total})`, Math.round((contractsDone / Math.max(total, 1)) * 45))
          }),
          3,
        )
        log(2, `Contracts built (${Object.keys(contract).length}/${total})`, 45)
        ensureNotAborted()

        // Intermediate save under contractDocId — shared across voice/subs variants
        await LocalWorkspace.upsertAnalysis({
          documentId: contractDocId,
          projectId: input.projectId,
          mediaFileId: input.mediaFileId,
          fileName: input.fileName,
          filePath: input.mediaPath,
          sizeBytes: input.sizeBytes,
          durationSeconds: input.durationSec,
          settings: input.settings,
          contract,
          artifacts: LocalWorkspace.buildDocumentArtifacts(contractDocId, contract),
          contractCurrent: false,
        })
      } else {
        contract = resumeContract!
        log(2, 'Reusing existing contracts', 45)
      }

      // ── Stage 3: Translation ─────────────────────────────────────
      const BACKEND_PROVIDERS = new Set(['m2m100', 'gpt', 'deepl', 'lara'])
      const providerIsOriginal = provider === 'original'

      let translations: Record<string, string> = {}
      if (resumePoint === 'tts' && resumeTranslations) {
        translations = resumeTranslations
        log(2, 'Reusing existing translations', 100)
      } else if (providerIsOriginal) {
        // "Original only" — no translation; Russian text stays empty
        log(2, 'Original language selected — skipping translation', 100)
      } else {
        const sentenceKeys = Object.keys(contract)
        if (sentenceKeys.length > 0) {
          log(2, `Translating sentences (0/${sentenceKeys.length})...`, 50)
          if (BACKEND_PROVIDERS.has(provider)) {
            // Translate via backend in parallel batches to avoid Cloudflare's 100s timeout.
            // Each batch of BATCH_SIZE sentences is a separate request; up to CONCURRENCY run at once.
            const BATCH_SIZE = 8
            const CONCURRENCY = 3
            const enabledProvider = input.translatorOptions?.find((p: { id: string }) => p.id === provider)
            const credentials = (enabledProvider as any)?.credentials || {}
            const batches: string[][] = []
            for (let i = 0; i < sentenceKeys.length; i += BATCH_SIZE) {
              batches.push(sentenceKeys.slice(i, i + BATCH_SIZE))
            }
            let batchesDone = 0
            await runConcurrent(
              batches.map((batch) => async () => {
                ensureNotAborted()
                const result = await requestJson<{ translations: Record<string, string> }>(
                  apiUrl('/api/translate'),
                  {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ sentences: batch, provider, credentials }),
                    signal: input.signal,
                  },
                ).catch((err: unknown) => {
                  if (err instanceof DOMException && err.name === 'AbortError') throw err
                  recordRuntimeDiagnostic('api.media.backend', 'translate.error', String(err instanceof Error ? err.message : err), 'error')
                  log(2, `Translation error: ${err instanceof Error ? err.message : String(err)}`, 50)
                  return { translations: {} as Record<string, string> }
                })
                Object.assign(translations, result.translations || {})
                batchesDone += batch.length
                log(2, `Translating sentences (${batchesDone}/${sentenceKeys.length})`, 50 + Math.round((batchesDone / Math.max(sentenceKeys.length, 1)) * 48))
              }),
              CONCURRENCY,
            )
            log(2, `Translated ${Object.keys(translations).length}/${sentenceKeys.length} sentences`, 98)
          } else {
            // Default: use local opus-mt-en-ru model in browser worker
            translations = await this.clientTranslateAnalysis(
              contractDocId,
              contract,
              (done, ttl) => log(2, `Translating sentences (${done}/${ttl})`, 50 + Math.round((done / Math.max(ttl, 1)) * 48)),
              input.signal,
            ).catch((err: unknown) => {
              if (err instanceof DOMException && err.name === 'AbortError') throw err
              recordRuntimeDiagnostic('api.media.backend', 'translate.error', String(err instanceof Error ? err.message : err), 'error')
              log(2, `Translation error: ${err instanceof Error ? err.message : String(err)}`, 50)
              return {}
            })
          }
        }
        log(2, 'Translation complete', 100)
        // Save translated contract at contractDocId so future runs with a different
        // voice/subtitles can resume from 'tts' without re-translating.
        if (Object.keys(translations).length > 0) {
          await LocalWorkspace.upsertAnalysis({
            documentId: contractDocId,
            projectId: input.projectId,
            mediaFileId: input.mediaFileId,
            fileName: input.fileName,
            filePath: input.mediaPath,
            sizeBytes: input.sizeBytes,
            durationSeconds: input.durationSec,
            settings: input.settings,
            contract,
            artifacts: LocalWorkspace.buildDocumentArtifacts(contractDocId, contract),
            contractCurrent: false,
          }).catch(() => { /* best-effort */ })
        }
      }
      ensureNotAborted()

      // ── Stage 4: Backend render (TTS + audio assembly + video) ───────────────
      const TEXT_SOURCE_TYPES = new Set(['text', 'pdf', 'docx', 'doc'])
      if (sourceType === 'audio' || sourceType === 'video' || TEXT_SOURCE_TYPES.has(sourceType)) {
        const voiceForCache = String(input.voiceChoice || '').trim().toLowerCase() === 'backend_svetlana' ? 'female' : 'male'
        const timedSentences = sentences.map((sent) => ({
          text_eng: sent.text,
          text_ru: String(translations[sent.text] || ''),
          start_ms: typeof sent.start_sec === 'number' ? Math.round(sent.start_sec * 1000) : null,
          end_ms: typeof sent.end_sec === 'number' ? Math.round(sent.end_sec * 1000) : null,
        }))

        const [existingAudio, existingVideo] = await Promise.all([
          LocalWorkspace.getAnalysisArtifactBlob(documentId, 'translated_audio_ru.mp3'),
          LocalWorkspace.getAnalysisArtifactBlob(documentId, 'translated_video_ru.mp4'),
        ])
        const needAudio = !existingAudio
        const needVideo = !existingVideo

        try {
          let audioBlob: Blob = existingAudio ?? new Blob([], { type: 'audio/mpeg' })
          let videoBlob: Blob = existingVideo ?? new Blob([], { type: 'video/mp4' })
          const artifactMapSrt = new Map<string, DocumentArtifact>()

          if (needAudio || needVideo) {
            log(3, 'Sending to server for rendering…', 5)
            const form = new FormData()
            form.append('meta', JSON.stringify({
              sentences: timedSentences,
              voice: voiceForCache,
              subtitlesMode: input.subtitlesMode || 'bilingual',
              need_audio: needAudio,
              need_video: needVideo,
            }))
            try {
              const srcBlob = await LocalWorkspace.getCachedUploadedMedia(input.mediaPath)
              if (srcBlob) form.append('audio', srcBlob, 'source.bin')
            } catch { /* non-fatal — backend falls back to TTS-only */ }
            const renderRes = await fetchWithRetry(
              apiUrl('/api/render-media'),
              {
                method: 'POST',
                body: form,
                signal: input.signal,
              },
              { retries: 0 },
            )
            if (!renderRes.ok) {
              const txt = await renderRes.text().catch(() => '')
              throw new Error(`Backend render failed: HTTP ${renderRes.status}: ${txt}`)
            }

            log(3, 'Downloading rendered artifacts…', 50)
            const zipBuf = await renderRes.arrayBuffer()
            const files = parseStoredZip(zipBuf)

            const getFileBytes = (name: string): ArrayBuffer => (files.get(name) ?? new Uint8Array(0)).buffer as ArrayBuffer
            if (needAudio) audioBlob = new Blob([getFileBytes('translated_audio_ru.mp3')], { type: 'audio/mpeg' })
            if (needVideo) videoBlob = new Blob([getFileBytes('translated_video_ru.mp4')], { type: 'video/mp4' })
            const srtEn = new TextDecoder().decode(files.get('subtitles_en.srt') ?? new Uint8Array())
            const srtBilingual = new TextDecoder().decode(files.get('subtitles_bilingual.srt') ?? new Uint8Array())
            const srtTarget = new TextDecoder().decode(files.get('subtitles_target.srt') ?? new Uint8Array())
            ensureNotAborted()

            artifactMapSrt.set('subtitles_en.srt', { name: 'subtitles_en.srt', size_bytes: srtEn.length, download_url: encodeTextArtifact('text/plain', srtEn) })
            artifactMapSrt.set('subtitles_bilingual.srt', { name: 'subtitles_bilingual.srt', size_bytes: srtBilingual.length, download_url: encodeTextArtifact('text/plain', srtBilingual) })
            artifactMapSrt.set('subtitles_target.srt', { name: 'subtitles_target.srt', size_bytes: srtTarget.length, download_url: encodeTextArtifact('text/plain', srtTarget) })
          }

          ensureNotAborted()

          log(4, 'Saving audio…', 92)
          if (needAudio) await LocalWorkspace.cacheAnalysisArtifactBlob(documentId, 'translated_audio_ru.mp3', audioBlob)
          log(4, 'Saving video…', 95)
          if (needVideo) await LocalWorkspace.cacheAnalysisArtifactBlob(documentId, 'translated_video_ru.mp4', videoBlob)

          const artifactMap = new Map<string, DocumentArtifact>(
            LocalWorkspace.buildDocumentArtifacts(documentId, contract).map((row) => [row.name, row]),
          )
          for (const [k, v] of artifactMapSrt) artifactMap.set(k, v)

          log(4, 'Saving analysis…', 98)
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
          log(4, 'Artifacts saved', 100)
        } catch (renderErr) {
          if (renderErr instanceof DOMException && renderErr.name === 'AbortError') throw renderErr
          console.error('[Render] FAILED:', renderErr instanceof Error ? renderErr.stack || renderErr.message : renderErr)
          recordRuntimeDiagnostic('api.media.backend', 'render.error', String(renderErr instanceof Error ? renderErr.message : renderErr), 'error')
          log(4, 'Media render failed — analysis saved without audio', 100)
          try {
            await LocalWorkspace.upsertAnalysis({
              documentId, projectId: input.projectId, mediaFileId: input.mediaFileId,
              fileName: input.fileName, filePath: input.mediaPath, sizeBytes: input.sizeBytes,
              durationSeconds: input.durationSec, settings: input.settings, contract,
              artifacts: LocalWorkspace.buildDocumentArtifacts(documentId, contract),
              contractCurrent: true,
            })
          } catch { /* ignore secondary save failure */ }
        }
      } else {
        log(4, 'Text analysis complete', 100)
      }

      recordRuntimeDiagnostic('api.media.backend', 'submit.success', { documentId, sentences: Object.keys(contract).length })
      return finish({
        result: { route: 'local', status: 'completed_local', document_id: documentId, message: 'Analysis completed.', stage_name: 'completed' },
        ui_feedback: { severity: 'info', title: 'Analysis completed', message: 'Media analysis completed and saved locally.' },
      })
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') throw err
      const rawMessage = err instanceof Error ? err.message : String(err)
      const message = isPwaModelMissingError(err) ? PWA_INSTALL_MESSAGE : rawMessage
      recordRuntimeDiagnostic('api.media.backend', 'submit.error', rawMessage, 'error')
      return finish({
        result: { route: 'reject', status: 'rejected', message, stage_name: 'loading_file' },
        ui_feedback: { severity: 'error', title: 'AI models not installed', message },
      })
    }
  }

  private async clientTranscribeAudio(
    mediaBlob: Blob,
    fileName: string,
    onProgress: (msg: string, pct?: number) => void,
    signal?: AbortSignal,
  ): Promise<{ source_type: string; sentences: Array<{ text: string; start_sec: number | null; end_sec: number | null }> }> {
    const isVideo = mediaBlob.type.startsWith('video/') || /\.(mp4|mov|avi|mkv|webm)$/i.test(fileName)
    const source_type = isVideo ? 'video' : 'audio'

    // AudioContext is unavailable in Web Workers — decode and resample here in the
    // main thread, then pass a plain Float32Array at 16 kHz to the worker.
    // Passing a non-16kHz { array, sampling_rate } object to Transformers.js
    // causes Ze.subarray errors inside _call_whisper chunking logic.
    onProgress('Decoding audio…')
    console.log('[clientTranscribeAudio] decoding', fileName, mediaBlob.type, mediaBlob.size, 'bytes')
    const AudioCtx = (window as typeof window & { webkitAudioContext?: typeof AudioContext }).AudioContext
      ?? (window as typeof window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
    if (!AudioCtx) throw new Error('AudioContext is unavailable in this browser.')
    const audioCtx = new AudioCtx()
    const arrayBuffer = await mediaBlob.arrayBuffer()
    if (signal?.aborted) throw new DOMException('Analysis cancelled.', 'AbortError')
    const decoded = await audioCtx.decodeAudioData(arrayBuffer)
    await audioCtx.close().catch(() => undefined)
    if (signal?.aborted) throw new DOMException('Analysis cancelled.', 'AbortError')

    // Resample to 16 kHz mono using OfflineAudioContext
    const TARGET_SR = 16_000
    const numFrames = Math.ceil(decoded.duration * TARGET_SR)
    const offlineCtx = new OfflineAudioContext(1, numFrames, TARGET_SR)
    const src = offlineCtx.createBufferSource()
    src.buffer = decoded
    src.connect(offlineCtx.destination)
    src.start(0)
    const resampled = await offlineCtx.startRendering()
    const audio = new Float32Array(resampled.getChannelData(0))
    const sampling_rate = TARGET_SR
    console.log('[clientTranscribeAudio] decoded+resampled:', decoded.duration.toFixed(1), 's →', audio.length, 'samples @16kHz')

    if (signal?.aborted) throw new DOMException('Analysis cancelled.', 'AbortError')

    return new Promise((resolve, reject) => {
      const worker = new Worker(new URL('../workers/whisperWorker.ts', import.meta.url), { type: 'module' })
      const id = Math.random().toString(36).slice(2)
      const onAbort = (): void => { worker.terminate(); reject(new DOMException('Analysis cancelled.', 'AbortError')) }
      signal?.addEventListener('abort', onAbort)
      worker.onmessage = (ev: MessageEvent): void => {
        const msg = ev.data as { type: string; id: string; message?: string; pct?: number; fullText?: string; sentences?: Array<{ text: string; start_sec: number; end_sec: number }> }
        if (msg.id !== id) return
        if (msg.type === 'progress') {
          const pct = typeof msg.pct === 'number' ? Math.max(5, msg.pct) : 50
          onProgress(msg.message ?? 'Transcribing…', pct)
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

  async getSourceFileBlob(mediaPath: string): Promise<Blob | null> {
    return await LocalWorkspace.getCachedUploadedMedia(String(mediaPath || '').trim())
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
