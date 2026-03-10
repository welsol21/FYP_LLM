import type {
  AnalysisHistoryRow,
  AnalyzeTextPayload,
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
import { transcribeMediaBlob } from '../lib/clientAsr'

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

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init)
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`HTTP ${res.status}: ${text}`)
  }
  return (await res.json()) as T
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

function buildNonContractArtifacts(documentId: string, rawText: string, sentences: string[]): DocumentArtifact[] {
  const mediaSentences: ArtifactSentenceRow[] = sentences.map((sentence, idx) => {
    const startMs = idx * 3000
    const endMs = startMs + 2600
    return {
      sentence_idx: idx,
      sentence_text: sentence,
      sentence_hash: simpleHash(`${idx}:${sentence}`),
      text_eng: sentence,
      text_ru: '',
      start: startMs / 1000,
      end: endMs / 1000,
      start_ms: startMs,
      end_ms: endMs,
      units: [],
      units_ru: [],
    }
  })
  const links = mediaSentences.map((row) => ({
    sentence_idx: row.sentence_idx,
    sentence_hash: row.sentence_hash,
  }))
  const mediaContract = {
    document_id: documentId,
    source_type: 'audio',
    source_path: '',
    text_hash: simpleHash(rawText),
    media_sentences: mediaSentences,
  }
  const legacySegments = mediaSentences.map((row) => ({
    id: row.sentence_idx + 1,
    text_eng: row.text_eng,
    units: row.units,
    start: row.start,
    end: row.end,
    text_ru: row.text_ru,
    units_ru: row.units_ru,
  }))
  const stageManifest = {
    schema_version: 1,
    last_document_id: documentId,
    immutable: {
      source_type: mediaContract.source_type,
      text_hash: mediaContract.text_hash,
      media_sentences_count: mediaSentences.length,
      contract_sentences_count: 0,
    },
  }
  const addText = (name: string, mime: string, text: string): DocumentArtifact => ({
    name,
    size_bytes: bytesOfText(text),
    download_url: encodeTextArtifact(mime, text),
  })
  return [
    addText('full_text.txt', 'text/plain', rawText),
    addText('media_contract.json', 'application/json', JSON.stringify(mediaContract, null, 2)),
    addText('sentence_link.json', 'application/json', JSON.stringify(links, null, 2)),
    addText('semantic_units_runtime.json', 'application/json', JSON.stringify(legacySegments, null, 2)),
    addText('bilingual_objects_runtime.json', 'application/json', JSON.stringify(legacySegments, null, 2)),
    addText('subtitles_en.srt', 'application/x-subrip', buildSrt(mediaSentences, false)),
    addText('subtitles_bilingual.srt', 'application/x-subrip', buildSrt(mediaSentences, true)),
    addText(
      'subtitles_target.srt',
      'application/x-subrip',
      buildSrt(mediaSentences.map((row) => ({ ...row, text_eng: '' })), true),
    ),
    addText('stage_manifest.json', 'application/json', JSON.stringify(stageManifest, null, 2)),
  ]
}

async function extractRawTextFromBlob(blob: Blob, mediaPath: string): Promise<string> {
  const kind = inferSourceKind(mediaPath, blob.type)
  if (kind !== 'text') return ''
  const text = typeof (blob as Blob & { text?: () => Promise<string> }).text === 'function'
    ? await (blob as Blob & { text: () => Promise<string> }).text()
    : await new Response(blob).text()
  if (mediaPath.toLowerCase().endsWith('.srt') || mediaPath.toLowerCase().endsWith('.vtt')) {
    return normalizeText(stripSubtitleMarkup(text))
  }
  return normalizeText(text)
}

export class HttpRuntimeApi implements RuntimeApi {
  async getUiState(): Promise<RuntimeUiState> {
    return requestJson<RuntimeUiState>('/api/ui-state')
  }

  async listProjects(): Promise<ProjectRow[]> {
    return await LocalWorkspace.listProjects()
  }

  async createProject(name: string): Promise<ProjectRow> {
    return await LocalWorkspace.createProject(name)
  }

  async getSelectedProject(): Promise<SelectedProject> {
    return await LocalWorkspace.getSelectedProject()
  }

  async setSelectedProject(projectId: string): Promise<SelectedProject> {
    return await LocalWorkspace.setSelectedProject(projectId)
  }

  async uploadMedia(file: File): Promise<{ fileName: string; mediaPath: string; sizeBytes: number }> {
    const fileName = String(file.name || 'uploaded.bin')
    const localId = typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
    const mediaPath = `/client-media/${localId}/${fileName}`
    const uploaded = { fileName, mediaPath, sizeBytes: file.size }
    await LocalWorkspace.cacheUploadedMedia(uploaded.mediaPath, file)
    return uploaded
  }

  async registerMediaFile(input: {
    projectId: string
    name: string
    mediaPath: string
    sizeBytes: number
    durationSec?: number
  }): Promise<{ id: string; project_id: string; name: string; path: string; size_bytes?: number; duration_seconds?: number }> {
    const row = await LocalWorkspace.registerMediaFile(input)
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
    const selected = await LocalWorkspace.getSelectedProject()
    const projects = await LocalWorkspace.listProjects()
    const effectiveProjectId = input.projectId || selected.project_id || projects[0]?.id || ''
    const localFile = input.mediaFileId ? await LocalWorkspace.getFileById(input.mediaFileId) : null
    const fileName = localFile?.name || input.mediaPath.split('/').pop() || input.mediaPath
    const settings = `Transl: ${input.translationProvider || 'm2m100'} / Subs: ${input.subtitlesMode || 'bilingual'} / Voice: ${input.voiceChoice || 'male'} / Proc: ${input.forceFullReprocess ? 'force' : 'incremental'}`
    const startedAt = Date.now()
    const stageLogs: string[] = []
    const progress: number[] = [0, 0, 0, 0, 0]
    const log = (stage: number, text: string, pct: number): void => {
      progress[stage] = Math.max(progress[stage], Math.max(0, Math.min(100, Math.round(pct))))
      stageLogs.push(text)
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
      return finish({
        result: {
          route: 'reject',
          status: 'rejected',
          message: 'Client media blob not found in local cache.',
        },
        ui_feedback: {
          severity: 'error',
          title: 'Processing failed',
          message: 'Client media blob not found in local cache.',
        },
      })
    }

    log(0, 'Loading source file', 100)

    const sourceKind = inferSourceKind(input.mediaPath, mediaBlob.type)
    if ((sourceKind === 'audio' || sourceKind === 'video') && !input.forceFullReprocess) {
      const fallbackFile = input.mediaFileId ? await LocalWorkspace.getFileById(input.mediaFileId) : null
      const fallbackDocId = String(fallbackFile?.document_id || '').trim()
      if (fallbackDocId) {
        log(2, 'Incremental reuse: reusing last client analysis for this media file', 100)
        return finish({
          result: {
            route: 'local',
            status: 'completed_local',
            document_id: fallbackDocId,
            message: 'Incremental reuse: existing client analysis loaded.',
            stage_name: 'completed',
          },
          ui_feedback: {
            severity: 'info',
            title: 'Local processing completed',
            message: 'Incremental reuse: existing client analysis loaded.',
          },
        })
      }
    }

    let rawText = ''
    if (sourceKind === 'text') {
      rawText = await extractRawTextFromBlob(mediaBlob, input.mediaPath)
      log(1, 'Text extracted on client', 100)
    } else if (sourceKind === 'audio' || sourceKind === 'video') {
      try {
        rawText = normalizeText(
          await transcribeMediaBlob(mediaBlob, {
            onProgress: ({ message, progress }) => log(1, message, progress),
          }),
        )
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err)
        return finish({
          result: {
            route: 'reject',
            status: 'rejected',
            message,
            stage_name: 'transcribing_audio',
          },
          ui_feedback: {
            severity: 'error',
            title: 'Processing failed',
            message,
          },
        })
      }
    } else {
      rawText = await extractRawTextFromBlob(mediaBlob, input.mediaPath)
    }

    if (!rawText) {
      const reason = sourceKind === 'audio' || sourceKind === 'video'
        ? 'Client ASR returned empty transcript.'
        : 'Client could not extract text from source.'
      return finish({
        result: {
          route: 'reject',
          status: 'rejected',
          message: reason,
          stage_name: 'transcribing_audio',
        },
        ui_feedback: {
          severity: 'error',
          title: 'Processing failed',
          message: reason,
        },
      })
    }
    const sentences = splitIntoSentences(rawText)
    if (sentences.length === 0) {
      return finish({
        result: {
          route: 'reject',
          status: 'rejected',
          message: 'No sentences detected after client text extraction.',
          stage_name: 'translating_text',
        },
        ui_feedback: {
          severity: 'error',
          title: 'Processing failed',
          message: 'No sentences detected after client text extraction.',
        },
      })
    }

    log(2, `Prepared ${sentences.length} sentences`, 15)
    const contract: VisualizerPayload = {}
    const duplicateCounter = new Map<string, number>()
    let contractBuildError = ''
    for (let idx = 0; idx < sentences.length; idx += 1) {
      const sentenceText = sentences[idx]
      try {
        const payload = await requestJson<SentenceContractPayload>('/api/sentence-contract', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ sentenceText, sentenceIdx: idx }),
        })
        if (!payload?.sentence_node || typeof payload.sentence_node !== 'object') {
          throw new Error('Contract node is missing in /api/sentence-contract response.')
        }
        const baseKey = String(payload?.sentence_text || sentenceText).trim() || `sentence_${idx + 1}`
        const seen = duplicateCounter.get(baseKey) || 0
        duplicateCounter.set(baseKey, seen + 1)
        const key = seen === 0 ? baseKey : `${baseKey} #${seen + 1}`
        contract[key] = payload.sentence_node
        log(2, `Built sentence contract ${idx + 1}/${sentences.length}`, 15 + Math.round(((idx + 1) / sentences.length) * 85))
      } catch (err) {
        contractBuildError = err instanceof Error ? err.message : String(err)
        break
      }
    }

    if (contractBuildError) {
      const documentId = `doc-${typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
        ? crypto.randomUUID().replace(/-/g, '').slice(0, 12)
        : `${Date.now()}${Math.random().toString(16).slice(2, 8)}`}`
      const artifacts = buildNonContractArtifacts(documentId, rawText, sentences)
      await LocalWorkspace.upsertAnalysis({
        documentId,
        projectId: effectiveProjectId,
        mediaFileId: input.mediaFileId,
        fileName,
        filePath: input.mediaPath,
        sizeBytes: input.sizeBytes,
        durationSeconds: input.durationSec,
        settings,
        contract: {},
        artifacts,
        contractCurrent: false,
      })
      log(2, 'Backend contract is unavailable. Saved local non-contract artifacts only.', 100)
      log(3, 'Generating client artifacts', 100)
      log(4, 'Exporting client artifacts', 100)
      return finish({
        result: {
          route: 'local',
          status: 'completed_local_no_contract',
          message: 'Backend contract is unavailable. Analysis saved without contract.',
          stage_name: 'completed',
        },
        ui_feedback: {
          severity: 'warning',
          title: 'Local processing completed',
          message: 'Backend contract is unavailable. Analysis saved without contract.',
        },
      })
    }

    log(3, 'Generating client artifacts', 100)
    log(4, 'Exporting client artifacts', 100)

    const documentId = `doc-${typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
      ? crypto.randomUUID().replace(/-/g, '').slice(0, 12)
      : `${Date.now()}${Math.random().toString(16).slice(2, 8)}`}`
    const artifacts = LocalWorkspace.buildDocumentArtifacts(documentId, contract)
    await LocalWorkspace.upsertAnalysis({
      documentId,
      projectId: effectiveProjectId,
      mediaFileId: input.mediaFileId,
      fileName,
      filePath: input.mediaPath,
      sizeBytes: input.sizeBytes,
      durationSeconds: input.durationSec,
      settings,
      contract,
      artifacts,
    })

    return finish({
      result: {
        route: 'local',
        status: 'completed_local',
        document_id: documentId,
        message: 'Local processing completed.',
        stage_name: 'completed',
      },
      ui_feedback: {
        severity: 'info',
        title: 'Local processing completed',
        message: 'Local processing completed.',
      },
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
