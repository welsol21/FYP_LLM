import type {
  DocumentArtifact,
  MediaProgressPayload,
  MediaSubmissionPayload,
  VisualizerPayload,
} from '../api/runtimeApi'
import { requestJson } from '../lib/apiUtils'
import { LocalWorkspace } from '../lib/localWorkspace'
import { prewarmLocalAsr, transcribeMediaBlobDetailed } from '../lib/clientAsr'
import { isTauriRuntime } from '../lib/clientMode'
import { prewarmLocalMediaRenderer, prewarmLocalTts, renderTranslatedMediaArtifacts } from '../lib/clientMediaRender'
import { resolveDesktopRuntimeAssetUrl } from '../lib/desktopRuntime'
import type { ArtifactSentenceRow, TimedSentenceRow } from '../lib/mediaArtifacts'
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
} from '../lib/mediaArtifacts'
import { mlWorkerClient } from '../lib/mlWorkerClient'
import { recordRuntimeDiagnostic } from '../lib/runtimeDiagnostics'
import { configureTransformersEnvForMode } from '../lib/transformersEnv'

type SentenceContractPayload = {
  sentence_text?: string
  sentence_hash?: string
  sentence_node?: VisualizerPayload[string]
}

type TranslationPipeline = (input: string, options?: Record<string, unknown>) => Promise<unknown>
let translationPipelinePromise: Promise<TranslationPipeline> | null = null
let translationPipelineReady = false

function parseTranslationText(result: unknown): string {
  if (typeof result === 'string') return result.trim()
  if (Array.isArray(result)) {
    const first = result[0]
    if (first && typeof first === 'object') {
      const row = first as Record<string, unknown>
      if (typeof row.translation_text === 'string') return row.translation_text.trim()
      if (typeof row.generated_text === 'string') return row.generated_text.trim()
      if (typeof row.text === 'string') return row.text.trim()
    }
  }
  if (result && typeof result === 'object') {
    const row = result as Record<string, unknown>
    if (typeof row.translation_text === 'string') return row.translation_text.trim()
    if (typeof row.generated_text === 'string') return row.generated_text.trim()
    if (typeof row.text === 'string') return row.text.trim()
  }
  return ''
}

function withTimeout<T>(promise: Promise<T>, timeoutMs: number): Promise<T | null> {
  return new Promise((resolve) => {
    let settled = false
    const timer = window.setTimeout(() => {
      if (settled) return
      settled = true
      resolve(null)
    }, Math.max(1, timeoutMs))
    promise
      .then((value) => {
        if (settled) return
        settled = true
        window.clearTimeout(timer)
        resolve(value)
      })
      .catch(() => {
        if (settled) return
        settled = true
        window.clearTimeout(timer)
        resolve(null)
      })
  })
}

function buildNonContractArtifacts(
  documentId: string,
  rawText: string,
  sentences: string[],
  translatedSentences: string[],
  timedSentences?: TimedSentenceRow[],
): { artifacts: DocumentArtifact[]; mediaSentences: ArtifactSentenceRow[] } {
  const mediaSentences: ArtifactSentenceRow[] = buildMediaSentenceRows(sentences, translatedSentences, timedSentences)
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
  const addText = (name: string, mime: string, text: string): DocumentArtifact => ({
    name,
    size_bytes: bytesOfText(text),
    download_url: encodeTextArtifact(mime, text),
  })
  return {
    artifacts: [
      addText('full_text.txt', 'text/plain', rawText),
      addText('media_contract.json', 'application/json', JSON.stringify(mediaContract, null, 2)),
      addText('semantic_units_runtime.json', 'application/json', JSON.stringify(legacySegments, null, 2)),
      addText('bilingual_objects_runtime.json', 'application/json', JSON.stringify(legacySegments, null, 2)),
      addText('subtitles_en.srt', 'application/x-subrip', buildSrt(mediaSentences, false)),
      addText('subtitles_bilingual.srt', 'application/x-subrip', buildSrt(mediaSentences, true)),
      addText('subtitles_target.srt', 'application/x-subrip', buildSrt(mediaSentences.map((row) => ({ ...row, text_eng: '' })), true)),
    ],
    mediaSentences,
  }
}

async function persistRenderedMediaArtifacts(input: {
  documentId: string
  sourceBlob: Blob
  sourceKind: 'text' | 'audio' | 'video' | 'other'
  subtitlesMode?: string
  voiceChoice?: string
  mediaSentences: ArtifactSentenceRow[]
  log?: (message: string, progress: number) => void
}): Promise<{ subtitlesEn: string; subtitlesBilingual: string; subtitlesTarget: string } | null> {
  if (input.sourceKind !== 'audio' && input.sourceKind !== 'video') return null
  input.log?.(`Rendering media: mode=${String(input.subtitlesMode || 'bilingual_sequential')}, voice=${String(input.voiceChoice || 'male')}, sentences=${input.mediaSentences.length}`, 10)
  const rendered = await renderTranslatedMediaArtifacts({
    sourceBlob: input.sourceBlob,
    sourceKind: input.sourceKind,
    subtitlesMode: input.subtitlesMode,
    voiceChoice: input.voiceChoice,
    sentences: input.mediaSentences.map((row) => ({
      start_ms: row.start_ms,
      end_ms: row.end_ms,
      text_eng: row.text_eng,
      text_ru: row.text_ru,
    })),
    onProgress: (message, progress) => input.log?.(message, progress),
  })
  if (!rendered) return null
  await LocalWorkspace.cacheAnalysisArtifactBlob(input.documentId, 'translated_audio_ru.mp3', rendered.translatedAudio)
  await LocalWorkspace.cacheAnalysisArtifactBlob(input.documentId, 'translated_video_ru.mp4', rendered.translatedVideo)
  return {
    subtitlesEn: String(rendered.subtitlesEn || ''),
    subtitlesBilingual: String(rendered.subtitlesBilingual || ''),
    subtitlesTarget: String(rendered.subtitlesTarget || ''),
  }
}

function mergeTimedRowsWithTranslations(
  timedSentences: TimedSentenceRow[],
  translatedSentences: string[],
): ArtifactSentenceRow[] {
  return timedSentences.map((row, idx) => ({
    sentence_idx: idx,
    sentence_text: row.text,
    sentence_hash: simpleHash(`${idx}:${row.text}`),
    text_eng: row.text,
    text_ru: String(translatedSentences[idx] || '').trim(),
    start: row.start_ms / 1000,
    end: row.end_ms / 1000,
    start_ms: row.start_ms,
    end_ms: row.end_ms,
    units: [],
    units_ru: [],
  }))
}

function applyTranslationsToMediaSentences(
  mediaSentences: ArtifactSentenceRow[],
  translatedSentences: string[],
): ArtifactSentenceRow[] {
  return mediaSentences.map((row, idx) => ({
    ...row,
    text_ru: String(translatedSentences[idx] || row.text_ru || '').trim(),
  }))
}

async function getTranslationPipeline(): Promise<TranslationPipeline> {
  if (!translationPipelinePromise) {
    translationPipelinePromise = (async () => {
      const transformers = await import('@huggingface/transformers')
      const env = (transformers as unknown as { env?: Record<string, unknown> }).env
      await configureTransformersEnvForMode(env, 'desktop')
      const modelsRoot = await resolveDesktopRuntimeAssetUrl('modelsRoot')
      const modelId = 'm2m100_418M'
      if (env && typeof env === 'object') {
        ;(env as Record<string, unknown>).localModelPath = modelsRoot
      }
      recordRuntimeDiagnostic('desktop.translation', 'model.path', { modelsRoot, modelId })
      const pipelineFactory = (transformers as unknown as {
        pipeline: (task: string, model: string, opts?: Record<string, unknown>) => Promise<TranslationPipeline>
      }).pipeline
      const pipe = await pipelineFactory('translation', modelId, { quantized: true, local_files_only: true })
      translationPipelineReady = true
      return pipe
    })()
  }
  return translationPipelinePromise
}

export async function prewarmDesktopMediaRuntime(onProgress?: (message: string, progress: number) => void): Promise<void> {
  const progress = (message: string, pct: number): void => {
    onProgress?.(message, Math.max(0, Math.min(100, Math.round(pct))))
  }
  progress('Loading desktop translation model', 10)
  await getTranslationPipeline()
  progress('Loading desktop ASR model', 40)
  await prewarmLocalAsr({ onProgress: ({ message, progress: pct }) => progress(message, 40 + Math.round(pct * 0.2)) })
  progress('Loading desktop media renderer', 70)
  await prewarmLocalMediaRenderer((message, pct) => progress(message, 70 + Math.round(pct * 0.15)))
  progress('Loading desktop TTS model', 88)
  await prewarmLocalTts((message, pct) => progress(message, 88 + Math.round(pct * 0.1)))
  progress('Desktop runtime ready', 100)
}

async function translateSentencesForArtifacts(
  sentences: string[],
  provider: string | undefined,
  log?: (message: string, progress: number) => void,
): Promise<string[]> {
  const providerId = String(provider || '').trim().toLowerCase()
  if (!sentences.length) return []
  if (!providerId || providerId === 'original' || providerId === 'none') return sentences.map(() => '')
  if (!['m2m100', 'hf', 'huggingface'].includes(providerId)) return sentences.map(() => '')
  if (import.meta.env.MODE === 'test') return sentences.map((s) => s)

  // In Tauri desktop mode, offload translation to the ML worker thread.
  if (isTauriRuntime()) {
    const modelPath = await resolveDesktopRuntimeAssetUrl('translation')
    log?.('Loading local translation model', 20)
    const results = await mlWorkerClient.runTranslate(sentences, modelPath, log)
    log?.('Translation completed', 100)
    return results
  }

  const loadTimeoutMs = Number(import.meta.env?.VITE_CLIENT_TRANSLATION_LOAD_TIMEOUT_MS || 45000)
  const sentenceTimeoutMs = Number(import.meta.env?.VITE_CLIENT_TRANSLATION_SENTENCE_TIMEOUT_MS || 15000)
  log?.(translationPipelineReady ? 'Using cached local translation model' : 'Loading local translation model', translationPipelineReady ? 40 : 20)
  const pipe = await withTimeout(getTranslationPipeline(), loadTimeoutMs)
  if (!pipe) throw new Error('Local translation model is unavailable or timed out while loading.')
  log?.('Local translation model loaded', 40)
  const out: string[] = []
  for (let i = 0; i < sentences.length; i += 1) {
    const result = await withTimeout(
      pipe(sentences[i], { src_lang: 'en', tgt_lang: 'ru', max_length: 256 }),
      sentenceTimeoutMs,
    )
    if (result == null) throw new Error(`Local translation model timed out on sentence ${i + 1}.`)
    const translated = parseTranslationText(result)
    if (!translated) throw new Error(`Local translation model returned empty translation on sentence ${i + 1}.`)
    out.push(translated)
    log?.(`Translating ${i + 1}/${sentences.length}`, 40 + Math.round(((i + 1) / sentences.length) * 60))
  }
  return out
}

export async function submitMediaDesktop(input: {
  mediaPath: string
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
  const normalizedDesktopVoiceChoice = String(input.voiceChoice || 'client_male').trim().toLowerCase()
  const localVoiceChoice = normalizedDesktopVoiceChoice === 'client_svetlana' ? 'female' : 'male'
  recordRuntimeDiagnostic('api.media', 'submit.desktop_path', {
    mediaPath: input.mediaPath,
    voiceChoice: normalizedDesktopVoiceChoice,
    localVoiceChoice,
    translationProvider: input.translationProvider,
  })
  const startedAt = Date.now()
  const stageLogs: string[] = []
  const progress: number[] = [0, 0, 0, 0, 0]
  const stageNames = ['loading_file', 'transcribing_audio', 'linguistic_parsing', 'generating_media', 'exporting_files']
  let lastLoggedText = ''
  let mediaStageClosed = false
  const ensureNotAborted = (): void => {
    if (input.signal?.aborted) throw new DOMException('Analysis cancelled.', 'AbortError')
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
    return finish({
      result: { route: 'reject', status: 'rejected', message: detail },
      ui_feedback: { severity: 'error', title: 'Processing failed', message: `${detail}. Re-upload this file in Files and retry.` },
    })
  }

  log(0, 'Loading source file', 100)
  ensureNotAborted()

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
  let timedSentences: TimedSentenceRow[] = []
  if (sourceKind === 'text') {
    rawText = await extractRawTextFromBlob(mediaBlob, input.mediaPath)
    log(1, 'Text extracted on client', 100)
  } else if (sourceKind === 'audio' || sourceKind === 'video') {
    try {
      const asr = await transcribeMediaBlobDetailed(mediaBlob, {
        onProgress: ({ message, progress }) => log(1, message, progress),
      })
      ensureNotAborted()
      rawText = normalizeText(asr.text)
      timedSentences = (asr.sentences || [])
        .map((row) => ({
          text: normalizeText(row.text),
          start_ms: Math.max(0, Number(row.start_ms || 0)),
          end_ms: Math.max(0, Number(row.end_ms || 0)),
        }))
        .filter((row) => row.text && row.end_ms > row.start_ms)
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err)
      return finish({
        result: { route: 'reject', status: 'rejected', message, stage_name: 'transcribing_audio' },
        ui_feedback: { severity: 'error', title: 'Processing failed', message },
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
      result: { route: 'reject', status: 'rejected', message: reason, stage_name: 'transcribing_audio' },
      ui_feedback: { severity: 'error', title: 'Processing failed', message: reason },
    })
  }

  const sentences = timedSentences.length > 0 ? timedSentences.map((row) => row.text) : splitIntoSentences(rawText)
  if (sentences.length === 0) {
    return finish({
      result: { route: 'reject', status: 'rejected', message: 'No sentences detected after client text extraction.', stage_name: 'translating_text' },
      ui_feedback: { severity: 'error', title: 'Processing failed', message: 'No sentences detected after client text extraction.' },
    })
  }

  log(2, `Prepared ${sentences.length} sentences`, 15)
  ensureNotAborted()
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
      const baseKey = String(payload?.sentence_text || sentenceText).trim() || `sentence_${idx + 1}`
      const seen = duplicateCounter.get(baseKey) || 0
      duplicateCounter.set(baseKey, seen + 1)
      const key = seen === 0 ? baseKey : `${baseKey} #${seen + 1}`
      if (payload?.sentence_node && typeof payload.sentence_node === 'object') {
        contract[key] = payload.sentence_node
      }
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
    let translatedSentences: string[] = []
    try {
      translatedSentences = await translateSentencesForArtifacts(sentences, input.translationProvider, (message, progressValue) => log(2, message, progressValue))
      ensureNotAborted()
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err)
      log(3, `Translation failed: ${message}`, 100)
      return finish({
        result: { route: 'reject', status: 'rejected', message: `Translation failed: ${message}`, stage_name: 'generating_media' },
        ui_feedback: { severity: 'error', title: 'Processing failed', message: `Translation failed: ${message}` },
      })
    }
    const bundle = buildNonContractArtifacts(documentId, rawText, sentences, translatedSentences, timedSentences)
    const normalizedError = normalizeContractError()
    let subtitleBundle: { subtitlesEn: string; subtitlesBilingual: string; subtitlesTarget: string } | null = null
    try {
      log(3, 'Generating translated media artifacts', 8)
      subtitleBundle = await persistRenderedMediaArtifacts({
        documentId,
        sourceBlob: mediaBlob,
        sourceKind,
        subtitlesMode: input.subtitlesMode,
        voiceChoice: localVoiceChoice,
        mediaSentences: bundle.mediaSentences,
        log: (message, progressValue) => {
          const normalized = String(message || '').trim()
          const exportStage = normalized === 'Finalizing media artifacts' || normalized === 'Media artifacts exported'
          log(exportStage ? 4 : 3, normalized, progressValue)
        },
      })
      ensureNotAborted()
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err)
      log(3, `Media rendering failed: ${message}`, 100)
      return finish({
        result: { route: 'reject', status: 'rejected', message: `Media rendering failed: ${message}`, stage_name: 'generating_media' },
        ui_feedback: { severity: 'error', title: 'Processing failed', message: `Media rendering failed: ${message}` },
      })
    }
    if (subtitleBundle) {
      replaceTextArtifact(bundle.artifacts, 'subtitles_en.srt', 'application/x-subrip', subtitleBundle.subtitlesEn)
      replaceTextArtifact(bundle.artifacts, 'subtitles_bilingual.srt', 'application/x-subrip', subtitleBundle.subtitlesBilingual)
      replaceTextArtifact(bundle.artifacts, 'subtitles_target.srt', 'application/x-subrip', subtitleBundle.subtitlesTarget)
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
      contract: {},
      artifacts: bundle.artifacts,
      contractCurrent: false,
    })
    log(2, `Contract unavailable: ${normalizedError}`, 100)
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

  const documentId = `doc-${typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID().replace(/-/g, '').slice(0, 12)
    : `${Date.now()}${Math.random().toString(16).slice(2, 8)}`}`
  const artifacts = LocalWorkspace.buildDocumentArtifacts(documentId, contract)
  let mediaSentences = extractMediaSentencesFromArtifacts(artifacts)
  let translatedSentencesForMedia: string[] = []
  try {
    translatedSentencesForMedia = await translateSentencesForArtifacts(sentences, input.translationProvider, (message, progressValue) => log(2, message, progressValue))
    ensureNotAborted()
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err)
    log(2, `Translation failed: ${message}`, 100)
    return finish({
      result: { route: 'reject', status: 'rejected', message: `Translation failed: ${message}`, stage_name: 'linguistic_parsing' },
      ui_feedback: { severity: 'error', title: 'Processing failed', message: `Translation failed: ${message}` },
    })
  }
  if ((sourceKind === 'audio' || sourceKind === 'video') && timedSentences.length === sentences.length && timedSentences.length > 0) {
    mediaSentences = mergeTimedRowsWithTranslations(timedSentences, translatedSentencesForMedia)
  } else if (translatedSentencesForMedia.length > 0) {
    mediaSentences = applyTranslationsToMediaSentences(mediaSentences, translatedSentencesForMedia)
  }
  let subtitleBundle: { subtitlesEn: string; subtitlesBilingual: string; subtitlesTarget: string } | null = null
  try {
    log(3, 'Generating translated media artifacts', 8)
    subtitleBundle = await persistRenderedMediaArtifacts({
      documentId,
      sourceBlob: mediaBlob,
      sourceKind,
      subtitlesMode: input.subtitlesMode,
      voiceChoice: localVoiceChoice,
      mediaSentences,
      log: (message, progressValue) => {
        const normalized = String(message || '').trim()
        const exportStage = normalized === 'Finalizing media artifacts' || normalized === 'Media artifacts exported'
        log(exportStage ? 4 : 3, normalized, progressValue)
      },
    })
    ensureNotAborted()
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err)
    log(3, `Media rendering failed: ${message}`, 100)
    return finish({
      result: { route: 'reject', status: 'rejected', message: `Media rendering failed: ${message}`, stage_name: 'generating_media' },
      ui_feedback: { severity: 'error', title: 'Processing failed', message: `Media rendering failed: ${message}` },
    })
  }
  if (subtitleBundle) {
    replaceTextArtifact(artifacts, 'subtitles_en.srt', 'application/x-subrip', subtitleBundle.subtitlesEn)
    replaceTextArtifact(artifacts, 'subtitles_bilingual.srt', 'application/x-subrip', subtitleBundle.subtitlesBilingual)
    replaceTextArtifact(artifacts, 'subtitles_target.srt', 'application/x-subrip', subtitleBundle.subtitlesTarget)
  }
  log(3, 'Generating client artifacts', 100)
  log(4, 'Exporting client artifacts', 100)
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
