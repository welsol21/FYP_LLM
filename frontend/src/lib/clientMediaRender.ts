import { resolveDesktopRuntimeAssetUrl } from './desktopRuntime'
import { recordRuntimeDiagnostic } from './runtimeDiagnostics'
import { configureTransformersEnvForMode } from './transformersEnv'

type SourceKind = 'text' | 'audio' | 'video' | 'other'

type TimedSentence = {
  start_ms: number
  end_ms: number
  text_eng: string
  text_ru: string
}

type ProgressCb = (message: string, progress: number) => void

type RenderInput = {
  sourceBlob: Blob
  sourceKind: SourceKind
  subtitlesMode?: string
  voiceChoice?: string
  sentences: TimedSentence[]
  onProgress?: ProgressCb
}

type RenderOutput = {
  translatedAudio: Blob
  translatedVideo: Blob
  subtitlesEn: string
  subtitlesBilingual: string
  subtitlesTarget: string
}

type FfmpegInstance = {
  load: (input: Record<string, string>) => Promise<boolean | void>
  writeFile: (path: string, data: Uint8Array) => Promise<void>
  readFile: (path: string) => Promise<Uint8Array>
  exec: (args: string[]) => Promise<number>
  deleteFile: (path: string) => Promise<void>
}

type FfmpegModule = {
  FFmpeg: new () => FfmpegInstance
}

type FfmpegUtilModule = {
  fetchFile: (input: Blob | File | string | URL) => Promise<Uint8Array>
  toBlobURL: (url: string, mimeType: string) => Promise<string>
}

type TtsPipelineOutput = {
  audio: Float32Array
  sampling_rate: number
  toBlob?: () => Blob
}

type TtsPipeline = (text: string, options?: Record<string, unknown>) => Promise<TtsPipelineOutput>

let ffmpegReadyPromise: Promise<{ ffmpeg: FfmpegInstance; util: FfmpegUtilModule }> | null = null
let ffmpegRunQueue: Promise<void> = Promise.resolve()
let ttsPipelinePromise: Promise<TtsPipeline> | null = null

function progress(cb: ProgressCb | undefined, message: string, pct: number): void {
  cb?.(message, Math.max(0, Math.min(100, Math.round(pct))))
}

async function yieldToBrowser(): Promise<void> {
  await new Promise<void>((resolve) => window.setTimeout(resolve, 0))
}

function toSubtitleMode(mode: string | undefined): 'source' | 'target' | 'bilingual_simultaneous' | 'bilingual_sequential' {
  const raw = String(mode || '').trim().toLowerCase()
  if (raw === 'source' || raw === 'source_only' || raw === 'source only') return 'source'
  if (raw === 'target' || raw === 'target_only' || raw === 'target only') return 'target'
  if (raw === 'bilingual_simultaneous' || raw === 'bilingual simultaneous' || raw === 'simultaneous') return 'bilingual_simultaneous'
  return 'bilingual_sequential'
}

function normalizedVoiceChoice(choice: string | undefined): 'male' | 'female' {
  const raw = String(choice || '').trim().toLowerCase()
  return raw.startsWith('f') ? 'female' : 'male'
}

function resolveModeFlags(mode: ReturnType<typeof toSubtitleMode>): {
  includeSource: boolean
  includeTarget: boolean
  bilingualSimultaneous: boolean
} {
  if (mode === 'source') {
    return { includeSource: true, includeTarget: false, bilingualSimultaneous: false }
  }
  if (mode === 'target') {
    return { includeSource: false, includeTarget: true, bilingualSimultaneous: false }
  }
  if (mode === 'bilingual_simultaneous') {
    return { includeSource: true, includeTarget: true, bilingualSimultaneous: true }
  }
  return { includeSource: true, includeTarget: true, bilingualSimultaneous: false }
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

function pushCue(blocks: string[], idx: number, startMs: number, endMs: number, lines: string[]): void {
  const cleanLines = lines.map((line) => String(line || '').trim()).filter(Boolean)
  if (!cleanLines.length) return
  blocks.push(
    [
      String(idx),
      `${formatSrtTime(startMs)} --> ${formatSrtTime(Math.max(endMs, startMs + 300))}`,
      ...cleanLines,
      '',
    ].join('\n'),
  )
}

function buildSubtitleSrt(sentences: TimedSentence[], mode: string | undefined): string {
  const resolved = toSubtitleMode(mode)
  const blocks: string[] = []
  let cue = 1
  for (const row of sentences) {
    const startMs = Math.max(0, Number(row.start_ms || 0))
    const endMs = Math.max(startMs + 300, Number(row.end_ms || 0))
    const textEn = String(row.text_eng || '').trim()
    const textRu = String(row.text_ru || '').trim()

    if (resolved === 'source') {
      if (textEn) {
        pushCue(blocks, cue, startMs, endMs, [textEn])
        cue += 1
      }
      continue
    }

    if (resolved === 'target') {
      if (textRu) {
        pushCue(blocks, cue, startMs, endMs, [textRu])
        cue += 1
      }
      continue
    }

    if (textEn && textRu) {
      pushCue(blocks, cue, startMs, endMs, [textEn, textRu])
      cue += 1
      continue
    }
    if (textEn) {
      pushCue(blocks, cue, startMs, endMs, [textEn])
      cue += 1
    }
    if (textRu) {
      pushCue(blocks, cue, startMs, endMs, [textRu])
      cue += 1
    }
  }
  return blocks.join('\n')
}

function rawAudioToWavBlob(samples: Float32Array, sampleRate: number): Blob {
  const numSamples = samples.length
  const dataSize = numSamples * 2
  const buffer = new ArrayBuffer(44 + dataSize)
  const view = new DataView(buffer)

  const writeString = (offset: number, value: string): void => {
    for (let i = 0; i < value.length; i += 1) {
      view.setUint8(offset + i, value.charCodeAt(i))
    }
  }

  writeString(0, 'RIFF')
  view.setUint32(4, 36 + dataSize, true)
  writeString(8, 'WAVE')
  writeString(12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true)
  view.setUint16(22, 1, true)
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * 2, true)
  view.setUint16(32, 2, true)
  view.setUint16(34, 16, true)
  writeString(36, 'data')
  view.setUint32(40, dataSize, true)

  let offset = 44
  for (let i = 0; i < numSamples; i += 1) {
    const clamped = Math.max(-1, Math.min(1, samples[i]))
    const int16 = clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff
    view.setInt16(offset, int16, true)
    offset += 2
  }
  return new Blob([buffer], { type: 'audio/wav' })
}

async function ensureTtsPipeline(onProgress?: ProgressCb): Promise<TtsPipeline> {
  if (!ttsPipelinePromise) {
    ttsPipelinePromise = (async () => {
      try {
        progress(onProgress, 'Loading local TTS model', 22)
        const startedAt = Date.now()
        const heartbeat = window.setInterval(() => {
          const elapsedSec = Math.max(1, Math.floor((Date.now() - startedAt) / 1000))
          progress(onProgress, `Loading local TTS model (${elapsedSec}s)`, 22)
        }, 3000)
        try {
        const transformers = await import('@huggingface/transformers')
        const env = (transformers as unknown as { env?: Record<string, unknown> }).env
        configureTransformersEnvForMode(env, 'desktop')
        const pipelineFactory = (transformers as unknown as {
          pipeline: (task: string, model: string, options?: Record<string, unknown>) => Promise<TtsPipeline>
        }).pipeline
        const modelsRoot = await resolveDesktopRuntimeAssetUrl('modelsRoot')
        const modelId = 'mms-tts-rus'
        if (env && typeof env === 'object') {
          ;(env as Record<string, unknown>).localModelPath = modelsRoot
        }
        recordRuntimeDiagnostic('desktop.tts', 'model.path', { modelsRoot, modelId })
        await yieldToBrowser()
        const tts = await pipelineFactory('text-to-speech', modelId, { quantized: true, local_files_only: true })
          progress(onProgress, 'Local TTS model loaded', 30)
          await yieldToBrowser()
          return tts
        } finally {
          window.clearInterval(heartbeat)
        }
      } catch (err) {
        ttsPipelinePromise = null
        throw err
      }
    })()
  }
  return await ttsPipelinePromise
}

export async function prewarmLocalTts(onProgress?: ProgressCb): Promise<void> {
  await ensureTtsPipeline(onProgress)
}

async function ensureFfmpeg(onProgress?: ProgressCb): Promise<{ ffmpeg: FfmpegInstance; util: FfmpegUtilModule }> {
  if (!ffmpegReadyPromise) {
    ffmpegReadyPromise = (async () => {
      try {
        progress(onProgress, 'Loading local media renderer', 4)
        const [{ FFmpeg }, util] = (await Promise.all([
          import('@ffmpeg/ffmpeg') as unknown as Promise<FfmpegModule>,
          import('@ffmpeg/util') as Promise<FfmpegUtilModule>,
        ]))

        const ffmpeg = new FFmpeg()
        const baseUrl = await resolveDesktopRuntimeAssetUrl('ffmpeg')
        recordRuntimeDiagnostic('desktop.ffmpeg', 'core.path', { baseUrl })
        const coreURL = await util.toBlobURL(`${baseUrl}/ffmpeg-core.js`, 'text/javascript')
        const wasmURL = await util.toBlobURL(`${baseUrl}/ffmpeg-core.wasm`, 'application/wasm')

        await yieldToBrowser()
        await ffmpeg.load({ coreURL, wasmURL })
        progress(onProgress, 'Local media renderer loaded', 12)
        await yieldToBrowser()
        return { ffmpeg, util }
      } catch (err) {
        ffmpegReadyPromise = null
        throw err
      }
    })()
  }
  return await ffmpegReadyPromise
}

export async function prewarmLocalMediaRenderer(onProgress?: ProgressCb): Promise<void> {
  await ensureFfmpeg(onProgress)
}

function extensionForBlob(blob: Blob, fallback = 'bin'): string {
  const mime = String(blob.type || '').toLowerCase()
  if (mime.includes('audio/mpeg')) return 'mp3'
  if (mime.includes('audio/wav')) return 'wav'
  if (mime.includes('audio/x-wav')) return 'wav'
  if (mime.includes('audio/mp4')) return 'm4a'
  if (mime.includes('audio/webm')) return 'webm'
  if (mime.includes('video/mp4')) return 'mp4'
  if (mime.includes('video/webm')) return 'webm'
  return fallback
}

function secondsFromMs(ms: number): string {
  return `${Math.max(0, ms) / 1000}`
}

async function safeDelete(ffmpeg: FfmpegInstance, path: string): Promise<void> {
  try {
    await ffmpeg.deleteFile(path)
  } catch {
    // ignore
  }
}

async function runQueued<T>(fn: () => Promise<T>): Promise<T> {
  const prev = ffmpegRunQueue
  let unlock!: () => void
  ffmpegRunQueue = new Promise<void>((resolve) => {
    unlock = resolve
  })
  await prev
  try {
    return await fn()
  } finally {
    unlock()
  }
}

async function runWithProgressPulse<T>(
  work: Promise<T>,
  onProgress: ProgressCb | undefined,
  message: string,
  startPct: number,
  endPct: number,
  tickMs = 1500,
): Promise<T> {
  let pct = startPct
  progress(onProgress, message, pct)
  const timer = window.setInterval(() => {
    pct = Math.min(endPct, pct + 1)
    progress(onProgress, message, pct)
  }, Math.max(250, tickMs))
  try {
    return await work
  } finally {
    window.clearInterval(timer)
  }
}

async function createSilentWavSegment(ffmpeg: FfmpegInstance, durationMs: number, outPath: string): Promise<void> {
  const safeMs = Math.max(1, Math.round(durationMs))
  await runCommand(
    ffmpeg,
    [
      '-y',
      '-f', 'lavfi',
      '-i', 'anullsrc=r=24000:cl=mono',
      '-t', secondsFromMs(safeMs),
      '-ac', '1',
      '-ar', '24000',
      '-c:a', 'pcm_s16le',
      outPath,
    ],
    `Silent wav rendering ${outPath}`,
  )
}

async function runCommand(ffmpeg: FfmpegInstance, args: string[], errorLabel: string): Promise<void> {
  const code = await ffmpeg.exec(args)
  if (code !== 0) {
    throw new Error(`${errorLabel} failed (ffmpeg exit code ${code})`)
  }
}

function isMediaKind(kind: SourceKind): kind is 'audio' | 'video' {
  return kind === 'audio' || kind === 'video'
}

const LATIN_DIGRAPH_MAP: Array<[RegExp, string]> = [
  [/shch/gi, 'щ'],
  [/sch/gi, 'щ'],
  [/yo/gi, 'ё'],
  [/yu/gi, 'ю'],
  [/ya/gi, 'я'],
  [/zh/gi, 'ж'],
  [/kh/gi, 'х'],
  [/ts/gi, 'ц'],
  [/ch/gi, 'ч'],
  [/sh/gi, 'ш'],
  [/ph/gi, 'ф'],
  [/th/gi, 'т'],
  [/qu/gi, 'кв'],
]

const LATIN_CHAR_MAP: Record<string, string> = {
  a: 'а',
  b: 'б',
  c: 'к',
  d: 'д',
  e: 'е',
  f: 'ф',
  g: 'г',
  h: 'х',
  i: 'и',
  j: 'дж',
  k: 'к',
  l: 'л',
  m: 'м',
  n: 'н',
  o: 'о',
  p: 'п',
  q: 'к',
  r: 'р',
  s: 'с',
  t: 'т',
  u: 'у',
  v: 'в',
  w: 'в',
  x: 'кс',
  y: 'й',
  z: 'з',
}

function transliterateLatinTokenToCyrillic(token: string): string {
  let out = String(token || '')
  for (const [pattern, replacement] of LATIN_DIGRAPH_MAP) {
    out = out.replace(pattern, replacement)
  }
  out = out.replace(/[A-Za-z]/g, (char) => LATIN_CHAR_MAP[char.toLowerCase()] || char)
  return out
}

function prepareRussianTtsText(text: string): string {
  return String(text || '').replace(/[A-Za-z][A-Za-z'.-]*/g, (token) => transliterateLatinTokenToCyrillic(token))
}

async function synthesizeTargetSegment(textForTts: string, sentenceIdx: number, sentenceTotal: number, onProgress?: ProgressCb): Promise<{ wav: Blob; durationMs: number; text: string }> {
  const tts = await ensureTtsPipeline(onProgress)
  const text = String(textForTts || '').trim()
  if (!text) {
    throw new Error(`Translated sentence ${sentenceIdx + 1} is empty, TTS cannot continue.`)
  }
  const preparedText = prepareRussianTtsText(text)
  progress(onProgress, `Synthesizing speech ${sentenceIdx + 1}/${sentenceTotal}`, 30 + Math.round(((sentenceIdx + 1) / Math.max(1, sentenceTotal)) * 24))
  await yieldToBrowser()
  const raw = await tts(preparedText)
  const sampleRate = Number(raw?.sampling_rate || 16000)
  const samples = raw?.audio instanceof Float32Array ? raw.audio : new Float32Array(0)
  if (!samples.length) {
    throw new Error(`TTS returned empty audio for sentence ${sentenceIdx + 1}.`)
  }
  const wavBlob = typeof raw?.toBlob === 'function' ? raw.toBlob() : rawAudioToWavBlob(samples, sampleRate)
  const durMs = Math.max(350, Math.round((samples.length / Math.max(1, sampleRate)) * 1000))
  return {
    wav: wavBlob,
    durationMs: durMs,
    text,
  }
}

type TimelineSegment = {
  start_ms: number
  end_ms: number
  text_eng: string
  text_ru: string
}

type SentenceWindow = {
  text_eng: string
  text_ru: string
  source_start_ms: number | null
  source_end_ms: number | null
  target_start_ms: number | null
  target_end_ms: number | null
}

type SubtitleRow = {
  start_ms: number
  end_ms: number
  text_eng: string
  text_ru: string
}

async function readFsBlob(ffmpeg: FfmpegInstance, path: string, mime: string): Promise<Blob> {
  const bytes = await ffmpeg.readFile(path)
  const copy = new Uint8Array(bytes.byteLength)
  copy.set(bytes)
  return new Blob([copy], { type: mime })
}

async function probeBlobDurationMs(blob: Blob): Promise<number> {
  const Ctx = (globalThis as typeof globalThis & { webkitAudioContext?: typeof AudioContext }).AudioContext
    || (globalThis as typeof globalThis & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
  if (!Ctx) return 0
  const ctx = new Ctx()
  try {
    const arrayBuffer = typeof (blob as Blob & { arrayBuffer?: () => Promise<ArrayBuffer> }).arrayBuffer === 'function'
      ? await (blob as Blob & { arrayBuffer: () => Promise<ArrayBuffer> }).arrayBuffer()
      : await new Response(blob).arrayBuffer()
    const decoded = await ctx.decodeAudioData(arrayBuffer.slice(0))
    return Math.max(0, Math.round(decoded.duration * 1000))
  } catch {
    return 0
  } finally {
    await ctx.close().catch(() => undefined)
  }
}

function subtitleLinesForMode(row: SubtitleRow | null, mode: ReturnType<typeof toSubtitleMode>): string[] {
  if (!row) return []
  const textEn = String(row.text_eng || '').trim()
  const textRu = String(row.text_ru || '').trim()
  if (mode === 'source') return textEn ? [textEn] : []
  if (mode === 'target') return textRu ? [textRu] : []
  return [textEn, textRu].filter(Boolean)
}

function findActiveSubtitleRow(rows: SubtitleRow[], timeMs: number): SubtitleRow | null {
  for (const row of rows) {
    if (timeMs >= row.start_ms && timeMs <= row.end_ms) return row
  }
  return null
}

function drawSubtitleOverlay(
  ctx: CanvasRenderingContext2D,
  width: number,
  height: number,
  lines: string[],
  mode: ReturnType<typeof toSubtitleMode>,
): void {
  if (!lines.length) return
  const baseFont = Math.max(24, Math.round(width * 0.024))
  const lineHeight = Math.round(baseFont * 1.3)
  const bottomPadding = Math.round(height * 0.08)
  const topPadding = Math.round(height * 0.08)
  const isSimultaneous = mode === 'bilingual_simultaneous' && lines.length >= 2

  const wrapText = (text: string): string[] => {
    const normalized = String(text || '').replace(/\s+/g, ' ').trim()
    if (!normalized) return []
    const words = normalized.split(' ')
    const maxWidth = width * 0.84
    const wrapped: string[] = []
    ctx.font = `700 ${baseFont}px Arial`
    let current = ''
    for (const word of words) {
      const candidate = current ? `${current} ${word}` : word
      if (ctx.measureText(candidate).width <= maxWidth) {
        current = candidate
        continue
      }
      if (current) wrapped.push(current)
      current = word
    }
    if (current) wrapped.push(current)
    return wrapped.slice(0, 4)
  }

  const drawBlock = (text: string, centerY: number): void => {
    const wrapped = wrapText(text)
    if (!wrapped.length) return
    ctx.font = `700 ${baseFont}px Arial`
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    const maxLineWidth = Math.max(...wrapped.map((line) => ctx.measureText(line).width))
    const boxWidth = Math.min(width * 0.9, maxLineWidth + 56)
    const boxHeight = wrapped.length * lineHeight + 24
    const boxX = (width - boxWidth) / 2
    const boxY = centerY - boxHeight / 2
    ctx.fillStyle = 'rgba(0, 0, 0, 0.68)'
    ctx.fillRect(boxX, boxY, boxWidth, boxHeight)
    ctx.fillStyle = '#ffffff'
    let lineY = centerY - ((wrapped.length - 1) * lineHeight) / 2
    for (const line of wrapped) {
      ctx.fillText(line, width / 2, lineY)
      lineY += lineHeight
    }
  }

  if (isSimultaneous) {
    drawBlock(lines[0], topPadding + lineHeight * 1.6)
    drawBlock(lines[1], height - bottomPadding - lineHeight * 1.6)
    return
  }

  const totalHeight = lines.length * lineHeight
  let startY = height - bottomPadding - totalHeight + lineHeight / 2
  for (const line of lines) {
    drawBlock(line, startY)
    startY += lineHeight
  }
}

async function waitForMediaEnded(media: HTMLMediaElement): Promise<void> {
  await new Promise<void>((resolve, reject) => {
    const onEnded = (): void => {
      cleanup()
      resolve()
    }
    const onError = (): void => {
      cleanup()
      reject(new Error('Media playback failed during canvas render.'))
    }
    const cleanup = (): void => {
      media.removeEventListener('ended', onEnded)
      media.removeEventListener('error', onError)
    }
    media.addEventListener('ended', onEnded)
    media.addEventListener('error', onError)
  })
}

async function renderVideoWithCanvas(input: {
  sourceBlob: Blob
  sourceKind: SourceKind
  translatedAudio: Blob
  subtitleRows: SubtitleRow[]
  mode: ReturnType<typeof toSubtitleMode>
  onProgress?: ProgressCb
}): Promise<Blob> {
  const canvas = document.createElement('canvas')
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('Canvas 2D context is unavailable.')

  const audioUrl = URL.createObjectURL(input.translatedAudio)
  const audioEl = document.createElement('audio')
  audioEl.src = audioUrl
  audioEl.preload = 'auto'
  audioEl.crossOrigin = 'anonymous'

  let videoEl: HTMLVideoElement | null = null
  let sourceUrl: string | null = null
  if (input.sourceKind === 'video') {
    sourceUrl = URL.createObjectURL(input.sourceBlob)
    videoEl = document.createElement('video')
    videoEl.src = sourceUrl
    videoEl.preload = 'auto'
    videoEl.muted = true
    videoEl.playsInline = true
    await new Promise<void>((resolve, reject) => {
      const onLoaded = (): void => {
        cleanup()
        resolve()
      }
      const onError = (): void => {
        cleanup()
        reject(new Error('Source video could not be loaded for canvas render.'))
      }
      const cleanup = (): void => {
        videoEl?.removeEventListener('loadedmetadata', onLoaded)
        videoEl?.removeEventListener('error', onError)
      }
      videoEl?.addEventListener('loadedmetadata', onLoaded)
      videoEl?.addEventListener('error', onError)
    })
    canvas.width = Math.max(640, videoEl.videoWidth || 1280)
    canvas.height = Math.max(360, videoEl.videoHeight || 720)
  } else {
    canvas.width = 1280
    canvas.height = 720
  }

  const AudioCtx = (globalThis as typeof globalThis & { webkitAudioContext?: typeof AudioContext }).AudioContext
    || (globalThis as typeof globalThis & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
  if (!AudioCtx) throw new Error('WebAudio is unavailable for video render.')
  const audioCtx = new AudioCtx()
  const destination = audioCtx.createMediaStreamDestination()
  const audioSource = audioCtx.createMediaElementSource(audioEl)
  audioSource.connect(destination)

  const canvasStream = canvas.captureStream(25)
  const mixedStream = new MediaStream([
    ...canvasStream.getVideoTracks(),
    ...destination.stream.getAudioTracks(),
  ])

  const mimeCandidates = [
    'video/webm;codecs=vp9,opus',
    'video/webm;codecs=vp8,opus',
    'video/webm',
  ]
  const mimeType = mimeCandidates.find((value) => {
    try {
      return typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported(value)
    } catch {
      return false
    }
  })
  if (!mimeType) throw new Error('MediaRecorder WebM is unavailable in this browser.')

  const chunks: BlobPart[] = []
  const recorder = new MediaRecorder(mixedStream, { mimeType })
  recorder.ondataavailable = (event) => {
    if (event.data && event.data.size > 0) chunks.push(event.data)
  }

  let rafId = 0
  let lastRenderPct = -1
  const drawFrame = (): void => {
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    if (videoEl && videoEl.readyState >= 2) {
      ctx.drawImage(videoEl, 0, 0, canvas.width, canvas.height)
    } else {
      ctx.fillStyle = '#000000'
      ctx.fillRect(0, 0, canvas.width, canvas.height)
    }
    const activeRow = findActiveSubtitleRow(input.subtitleRows, Math.round(audioEl.currentTime * 1000))
    const lines = subtitleLinesForMode(activeRow, input.mode)
    drawSubtitleOverlay(ctx, canvas.width, canvas.height, lines, input.mode)
    const duration = Math.max(0.001, audioEl.duration || 0)
    const renderPct = 76 + Math.min(14, Math.max(0, (audioEl.currentTime / duration) * 14))
    const roundedPct = Math.round(renderPct)
    if (roundedPct !== lastRenderPct) {
      lastRenderPct = roundedPct
      progress(input.onProgress, 'Rendering translated video track', roundedPct)
    }
    rafId = window.requestAnimationFrame(drawFrame)
  }

  recorder.start(250)
  drawFrame()
  progress(input.onProgress, 'Rendering translated video track', 76)
  await yieldToBrowser()
  await audioCtx.resume()
  if (videoEl) {
    void videoEl.play().catch(() => undefined)
  }
  await audioEl.play()
  await waitForMediaEnded(audioEl)
  window.cancelAnimationFrame(rafId)
  recorder.stop()
  await new Promise<void>((resolve) => {
    recorder.onstop = () => resolve()
  })

  audioSource.disconnect()
  destination.disconnect()
  mixedStream.getTracks().forEach((track) => track.stop())
  await audioCtx.close().catch(() => undefined)
  URL.revokeObjectURL(audioUrl)
  if (sourceUrl) URL.revokeObjectURL(sourceUrl)

  return new Blob(chunks, { type: mimeType })
}

function buildSimultaneousBilingualTimeline(windows: SentenceWindow[]): TimelineSegment[] {
  const out: TimelineSegment[] = []
  for (const row of windows) {
    const start = typeof row.source_start_ms === 'number'
      ? row.source_start_ms
      : row.target_start_ms
    const end = typeof row.target_end_ms === 'number'
      ? row.target_end_ms
      : row.source_end_ms
    if (typeof start !== 'number' || typeof end !== 'number') continue
    out.push({
      start_ms: start,
      end_ms: end,
      text_eng: String(row.text_eng || ''),
      text_ru: String(row.text_ru || ''),
    })
  }
  return out
}

export async function renderTranslatedMediaArtifacts(input: RenderInput): Promise<RenderOutput | null> {
  if (!isMediaKind(input.sourceKind)) return null

  if (import.meta.env.MODE === 'test') {
    const fallbackAudio = input.sourceBlob.type.startsWith('audio/')
      ? input.sourceBlob
      : new Blob([new Uint8Array([1, 2, 3, 4])], { type: 'audio/mpeg' })
    const fallbackVideo = new Blob([new Uint8Array([1, 2, 3, 4, 5, 6])], { type: 'video/mp4' })
    return {
      translatedAudio: fallbackAudio,
      translatedVideo: fallbackVideo,
      subtitlesEn: buildSubtitleSrt(input.sentences, 'source'),
      subtitlesBilingual: buildSubtitleSrt(input.sentences, 'bilingual_sequential'),
      subtitlesTarget: buildSubtitleSrt(input.sentences.map((row) => ({ ...row, text_eng: '' })), 'target'),
    }
  }

  return await runQueued(async () => {
    const { ffmpeg, util } = await ensureFfmpeg(input.onProgress)

    const mode = toSubtitleMode(input.subtitlesMode)
    const flags = resolveModeFlags(mode)
    const sourceExt = extensionForBlob(input.sourceBlob, input.sourceKind === 'video' ? 'mp4' : 'mp3')
    const sourceFile = `source.${sourceExt}`
    const subtitleFile = 'subs_current.srt'
    const audioFile = 'translated_audio_ru.mp3'
    const videoFile = 'translated_video_ru.mp4'

    progress(input.onProgress, 'Preparing media timeline', 20)
    await yieldToBrowser()
    await ffmpeg.writeFile(sourceFile, await util.fetchFile(input.sourceBlob))

    let currentMs = 0
    const segmentFiles: string[] = []
    const sourceSubtitleSegments: TimelineSegment[] = []
    const targetSubtitleSegments: TimelineSegment[] = []
    const sentenceWindows: SentenceWindow[] = []
    const bilingualSequentialSegments: TimelineSegment[] = []

    try {
      for (let i = 0; i < input.sentences.length; i += 1) {
        const row = input.sentences[i]
        const textEn = String(row.text_eng || '').trim()
        const textRu = String(row.text_ru || '').trim()
        const window: SentenceWindow = {
          text_eng: textEn,
          text_ru: textRu,
          source_start_ms: null,
          source_end_ms: null,
          target_start_ms: null,
          target_end_ms: null,
        }

        if (flags.includeSource) {
          const sourceStartMs = Math.max(0, Number(row.start_ms || 0))
          const sourceEndMs = Math.max(sourceStartMs + 300, Number(row.end_ms || 0))
          const sourceSegName = `src_${String(i + 1).padStart(4, '0')}.wav`
          progress(
            input.onProgress,
            `Rendering source segment ${i + 1}/${input.sentences.length}`,
            34 + Math.round(((i + 1) / Math.max(1, input.sentences.length)) * 12),
          )
          await yieldToBrowser()
          await runWithProgressPulse(
            runCommand(
              ffmpeg,
              [
                '-y',
                '-ss', secondsFromMs(sourceStartMs),
                '-to', secondsFromMs(sourceEndMs),
                '-i', sourceFile,
                '-vn',
                '-ac', '1',
                '-ar', '24000',
                '-c:a', 'pcm_s16le',
                sourceSegName,
              ],
              `Source segment rendering ${i + 1}`,
            ),
            input.onProgress,
            `Rendering source segment ${i + 1}/${input.sentences.length}`,
            34 + Math.round((i / Math.max(1, input.sentences.length)) * 12),
            34 + Math.round(((i + 1) / Math.max(1, input.sentences.length)) * 12),
            900,
          )
          segmentFiles.push(sourceSegName)
          const sourceBlob = await readFsBlob(ffmpeg, sourceSegName, 'audio/wav')
          const durationMs = Math.max(300, await probeBlobDurationMs(sourceBlob) || (sourceEndMs - sourceStartMs))
          const startMs = currentMs
          const endMs = startMs + durationMs
          sourceSubtitleSegments.push({ start_ms: startMs, end_ms: endMs, text_eng: textEn, text_ru: '' })
          window.source_start_ms = startMs
          window.source_end_ms = endMs
          if (!flags.bilingualSimultaneous) {
            bilingualSequentialSegments.push({ start_ms: startMs, end_ms: endMs, text_eng: textEn, text_ru: '' })
          }
          currentMs = endMs
        }

        if (flags.includeTarget) {
          const textForTts = textRu || textEn
          if (textForTts) {
            const leadSilenceMs = flags.includeSource ? 10 : 0
            if (leadSilenceMs > 0) {
              const leadSilenceName = `silence_lead_${String(i + 1).padStart(4, '0')}.wav`
              await createSilentWavSegment(ffmpeg, leadSilenceMs, leadSilenceName)
              segmentFiles.push(leadSilenceName)
              currentMs += leadSilenceMs
            }
            if (flags.bilingualSimultaneous && flags.includeSource) {
              const simSilenceName = `silence_sim_${String(i + 1).padStart(4, '0')}.wav`
              await createSilentWavSegment(ffmpeg, 10, simSilenceName)
              segmentFiles.push(simSilenceName)
              currentMs += 10
            }
            await yieldToBrowser()
            const target = await synthesizeTargetSegment(textForTts, i, input.sentences.length, input.onProgress)
            const targetInputWavName = `tgt_in_${String(i + 1).padStart(4, '0')}.wav`
            const targetWavName = `tgt_${String(i + 1).padStart(4, '0')}.wav`
            await ffmpeg.writeFile(targetInputWavName, await util.fetchFile(target.wav))
            await runWithProgressPulse(
              runCommand(
                ffmpeg,
                [
                  '-y',
                  '-i', targetInputWavName,
                  '-ac', '1',
                  '-ar', '24000',
                  '-c:a', 'pcm_s16le',
                  targetWavName,
                ],
                `Target segment normalization ${i + 1}`,
              ),
              input.onProgress,
              `Normalizing translated segment ${i + 1}/${input.sentences.length}`,
              46 + Math.round((i / Math.max(1, input.sentences.length)) * 10),
              46 + Math.round(((i + 1) / Math.max(1, input.sentences.length)) * 10),
              900,
            )
            await safeDelete(ffmpeg, targetInputWavName)
            segmentFiles.push(targetWavName)
            const targetBlob = await readFsBlob(ffmpeg, targetWavName, 'audio/wav')
            const targetDurationMs = Math.max(300, await probeBlobDurationMs(targetBlob) || target.durationMs)
            const startMs = currentMs
            const endMs = startMs + targetDurationMs
            targetSubtitleSegments.push({ start_ms: startMs, end_ms: endMs, text_eng: '', text_ru: target.text })
            window.target_start_ms = startMs
            window.target_end_ms = endMs
            if (!flags.bilingualSimultaneous) {
              bilingualSequentialSegments.push({ start_ms: startMs, end_ms: endMs, text_eng: '', text_ru: target.text })
            }
            currentMs = endMs
          }
        }

        sentenceWindows.push(window)

        if (i < input.sentences.length - 1) {
          const nextRow = input.sentences[i + 1]
          const sourceGapMs = Math.max(
            10,
            Math.floor((Math.max(0, Number(nextRow.start_ms || 0)) - Math.max(0, Number(row.end_ms || 0))) / 3),
          )
          const gapSegName = `silence_gap_${String(i + 1).padStart(4, '0')}.wav`
          await createSilentWavSegment(ffmpeg, sourceGapMs, gapSegName)
          segmentFiles.push(gapSegName)
          currentMs += sourceGapMs
        }
      }

      if (!segmentFiles.length) {
        throw new Error('No media segments were generated.')
      }

      const concatFile = 'tts_concat.txt'
      await ffmpeg.writeFile(concatFile, new TextEncoder().encode(segmentFiles.map((name) => `file '${name}'`).join('\n')))
      progress(input.onProgress, 'Concatenating final audio track', 58)
      await yieldToBrowser()
      await runWithProgressPulse(
        runCommand(
          ffmpeg,
          [
            '-y',
            '-f', 'concat',
            '-safe', '0',
            '-i', concatFile,
            '-ac', '1',
            '-ar', '24000',
            '-c:a', 'libmp3lame',
            '-q:a', '2',
            audioFile,
          ],
          'Final audio concatenation',
        ),
        input.onProgress,
        'Concatenating final audio track',
        58,
        68,
        900,
      )
      await safeDelete(ffmpeg, concatFile)
      for (const name of segmentFiles) await safeDelete(ffmpeg, name)

      const subtitlesEnRows = sourceSubtitleSegments.length > 0 ? sourceSubtitleSegments : bilingualSequentialSegments
      const simultaneousRows = flags.bilingualSimultaneous ? buildSimultaneousBilingualTimeline(sentenceWindows) : []
      const subtitlesBilingualRows = simultaneousRows.length > 0 ? simultaneousRows : bilingualSequentialSegments
      const subtitlesTargetRows = targetSubtitleSegments.length > 0
        ? targetSubtitleSegments
        : bilingualSequentialSegments.map((row) => ({ ...row, text_eng: '' }))

      const subtitlesEn = buildSubtitleSrt(subtitlesEnRows, 'source')
      const subtitlesBilingual = buildSubtitleSrt(
        subtitlesBilingualRows,
        flags.bilingualSimultaneous ? 'bilingual_simultaneous' : 'bilingual_sequential',
      )
      const subtitlesTarget = buildSubtitleSrt(subtitlesTargetRows, 'target')
      const selectedSubtitleRows = mode === 'source'
        ? subtitlesEnRows
        : mode === 'target'
          ? subtitlesTargetRows
          : subtitlesBilingualRows
      const selectedSubtitle = mode === 'source'
        ? subtitlesEn
        : mode === 'target'
          ? subtitlesTarget
          : subtitlesBilingual

      if (!selectedSubtitle.trim()) {
        throw new Error('Translated subtitles are empty; media export cannot proceed.')
      }
      await ffmpeg.writeFile(subtitleFile, new TextEncoder().encode(selectedSubtitle))

      progress(input.onProgress, 'Preparing translated video track', 74)
      await yieldToBrowser()
      const audioBlob = await readFsBlob(ffmpeg, audioFile, 'audio/mpeg')
      const renderedVideo = await renderVideoWithCanvas({
        sourceBlob: input.sourceBlob,
        sourceKind: input.sourceKind,
        translatedAudio: audioBlob,
        subtitleRows: selectedSubtitleRows,
        mode,
        onProgress: input.onProgress,
      })
      const renderedVideoInput = 'translated_video_input.webm'
      await ffmpeg.writeFile(renderedVideoInput, await util.fetchFile(renderedVideo))
      progress(input.onProgress, 'Encoding mp4 container', 92)
      await yieldToBrowser()
      await runWithProgressPulse(
        runCommand(
          ffmpeg,
          [
            '-y',
            '-i', renderedVideoInput,
            '-c:v', 'libx264',
            '-pix_fmt', 'yuv420p',
            '-preset', 'ultrafast',
            '-crf', '24',
            '-c:a', 'aac',
            '-b:a', '192k',
            '-movflags', '+faststart',
            videoFile,
          ],
          'Video remuxing',
        ),
        input.onProgress,
        'Encoding mp4 container',
        92,
        95,
        1200,
      )
      await safeDelete(ffmpeg, renderedVideoInput)
      progress(input.onProgress, 'Finalizing media artifacts', 96)
      await yieldToBrowser()

      const audioBytes = await ffmpeg.readFile(audioFile)
      const videoBytes = await ffmpeg.readFile(videoFile)
      progress(input.onProgress, 'Media artifacts exported', 100)
      await yieldToBrowser()

      const audioCopy = new Uint8Array(audioBytes.byteLength)
      audioCopy.set(audioBytes)
      const videoCopy = new Uint8Array(videoBytes.byteLength)
      videoCopy.set(videoBytes)
      return {
        translatedAudio: new Blob([audioCopy], { type: 'audio/mpeg' }),
        translatedVideo: new Blob([videoCopy], { type: 'video/mp4' }),
        subtitlesEn,
        subtitlesBilingual,
        subtitlesTarget,
      }
    } finally {
      await safeDelete(ffmpeg, sourceFile)
      await safeDelete(ffmpeg, subtitleFile)
      await safeDelete(ffmpeg, audioFile)
      await safeDelete(ffmpeg, videoFile)
    }

  })
}
