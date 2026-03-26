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
  /** If provided, called instead of local TTS model. Returns audio blob (any format ffmpeg can decode). */
  ttsProvider?: (idx: number, text: string) => Promise<Blob>
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
let ffmpegFontLoaded = false
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
          configureTransformersEnv(env)
          const pipelineFactory = (transformers as unknown as {
            pipeline: (task: string, model: string, options?: Record<string, unknown>) => Promise<TtsPipeline>
          }).pipeline
          const modelId = String(import.meta.env?.VITE_CLIENT_TTS_MODEL || 'Xenova/mms-tts-rus').trim()
          await yieldToBrowser()
          const tts = await pipelineFactory('text-to-speech', modelId, { quantized: true })
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
        const baseUrl = String(import.meta.env?.VITE_CLIENT_FFMPEG_CORE_BASE_URL || '/ffmpeg').trim()
        const coreURL = await util.toBlobURL(`${baseUrl}/ffmpeg-core.js`, 'text/javascript')
        const wasmURL = await util.toBlobURL(`${baseUrl}/ffmpeg-core.wasm`, 'application/wasm')

        // classWorkerURL must point to the bundled worker served from public/ffmpeg/.
        // Without this, Vite dev mode resolves new URL("./worker.js", import.meta.url)
        // to /node_modules/.vite/deps/worker.js (404) — ffmpeg.load() hangs forever.
        const workerURL = `${baseUrl}/ffmpeg-worker.js`
        await yieldToBrowser()
        await ffmpeg.load({ coreURL, wasmURL, classWorkerURL: workerURL })
        ;(ffmpeg as unknown as { on: (e: string, cb: (x: { message: string }) => void) => void })
          .on('log', ({ message }) => { if (message?.trim()) console.log('[FFmpeg-log]', message) })
        // Load DejaVuSans font into WASM VFS for drawtext subtitle rendering (Cyrillic support)
        try {
          const fontRes = await fetch(dejaVuSansUrl)
          const fontBytes = new Uint8Array(await fontRes.arrayBuffer())
          if (fontRes.ok && fontBytes.byteLength > 0) {
            await ffmpeg.writeFile('/DejaVuSans.ttf', fontBytes)
            ffmpegFontLoaded = true
            recordRuntimeDiagnostic('client.ffmpeg', 'font.loaded', { size: fontBytes.byteLength })
          } else {
            ffmpegFontLoaded = false
            recordRuntimeDiagnostic('client.ffmpeg', 'font.error', `HTTP ${fontRes.status}, size=${fontBytes.byteLength}`, 'warning')
          }
        } catch (err) {
          ffmpegFontLoaded = false
          recordRuntimeDiagnostic('client.ffmpeg', 'font.error', String(err instanceof Error ? err.message : err), 'warning')
        }
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
      '-i', 'anullsrc=r=16000:cl=mono',
      '-t', secondsFromMs(safeMs),
      '-ac', '1',
      '-ar', '16000',
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

async function synthesizeTargetSegmentPcm(
  textForTts: string,
  sentenceIdx: number,
  sentenceTotal: number,
  targetRate: number,
  onProgress?: ProgressCb,
): Promise<{ pcm: Float32Array; text: string }> {
  const tts = await ensureTtsPipeline(onProgress)
  const text = String(textForTts || '').trim()
  if (!text) {
    throw new Error(`Translated sentence ${sentenceIdx + 1} is empty, TTS cannot continue.`)
  }
  const preparedText = prepareRussianTtsText(text)
  progress(
    onProgress,
    `Synthesizing speech ${sentenceIdx + 1}/${sentenceTotal}`,
    30 + Math.round(((sentenceIdx + 1) / Math.max(1, sentenceTotal)) * 24),
  )
  await yieldToBrowser()
  const raw = await tts(preparedText)
  const sampleRate = Number(raw?.sampling_rate || 16000)
  const audio = raw?.audio instanceof Float32Array ? raw.audio : new Float32Array(0)
  if (!audio.length) {
    throw new Error(`TTS returned empty audio for sentence ${sentenceIdx + 1}.`)
  }
  const pcm = await resampleFloat32(audio, sampleRate, targetRate)
  return { pcm, text }
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

async function resampleFloat32(pcm: Float32Array, fromRate: number, toRate: number): Promise<Float32Array> {
  if (pcm.length === 0) return new Float32Array(0)
  if (Math.abs(fromRate - toRate) < 1) return pcm.slice()
  const frameCount = Math.ceil(pcm.length / fromRate * toRate)
  if (frameCount <= 0) return new Float32Array(0)
  const offlineCtx = new OfflineAudioContext(1, frameCount, toRate)
  const buf = offlineCtx.createBuffer(1, pcm.length, fromRate)
  buf.copyToChannel(pcm as Float32Array<ArrayBuffer>, 0)
  const src = offlineCtx.createBufferSource()
  src.buffer = buf
  src.connect(offlineCtx.destination)
  src.start(0)
  const rendered = await offlineCtx.startRendering()
  return rendered.getChannelData(0).slice()
}

async function decodeAudioBlobToBuffer(blob: Blob): Promise<AudioBuffer> {
  const ctx = new AudioContext()
  try {
    const ab = await blob.arrayBuffer()
    return await ctx.decodeAudioData(ab)
  } finally {
    await ctx.close().catch(() => {})
  }
}

async function decodeBlobToPcm(blob: Blob, targetRate: number): Promise<Float32Array> {
  const ctx = new AudioContext()
  try {
    const ab = await blob.arrayBuffer()
    const decoded = await ctx.decodeAudioData(ab)
    const mono = decoded.numberOfChannels > 1
      ? (() => {
          const ch0 = decoded.getChannelData(0)
          const ch1 = decoded.getChannelData(1)
          const mixed = new Float32Array(ch0.length)
          for (let i = 0; i < ch0.length; i += 1) mixed[i] = (ch0[i] + ch1[i]) * 0.5
          return mixed
        })()
      : decoded.getChannelData(0)
    return await resampleFloat32(mono, decoded.sampleRate, targetRate)
  } finally {
    await ctx.close().catch(() => {})
  }
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

export async function muxVideoWithAudio(
  sourceVideoBlob: Blob,
  audioBlob: Blob,
  onProgress?: ProgressCb,
): Promise<Blob> {
  return await runQueued(async () => {
    const { ffmpeg, util } = await ensureFfmpeg(onProgress)
    const videoExt = extensionForBlob(sourceVideoBlob, 'mp4')
    const audioExt = extensionForBlob(audioBlob, 'mp3')
    const inVideo = `mux_src.${videoExt}`
    const inAudio = `mux_audio.${audioExt}`
    const outFile = 'mux_out.mp4'

    progress(onProgress, 'Muxing video with translated audio', 5)
    await ffmpeg.writeFile(inVideo, await util.fetchFile(sourceVideoBlob))
    await ffmpeg.writeFile(inAudio, await util.fetchFile(audioBlob))

    progress(onProgress, 'Muxing video with translated audio', 15)
    await runWithProgressPulse(
      runCommand(
        ffmpeg,
        [
          '-y',
          '-i', inVideo,
          '-i', inAudio,
          '-map', '0:v:0',
          '-map', '1:a:0',
          '-c:v', 'copy',
          '-c:a', 'aac',
          '-b:a', '192k',
          '-shortest',
          '-movflags', '+faststart',
          outFile,
        ],
        'Video mux',
      ),
      onProgress,
      'Muxing video with translated audio',
      15,
      90,
      1000,
    )

    const bytes = await ffmpeg.readFile(outFile)
    const copy = new Uint8Array(bytes.byteLength)
    copy.set(bytes)
    await safeDelete(ffmpeg, inVideo)
    await safeDelete(ffmpeg, inAudio)
    await safeDelete(ffmpeg, outFile)
    progress(onProgress, 'Video mux complete', 100)
    return new Blob([copy], { type: 'video/mp4' })
  })
}

// ── FFmpeg drawtext subtitle filter ──────────────────────────────────────────

const DT_MARGIN_BOTTOM = 70
const DT_LINE_HEIGHT = 38
const DT_BLOCK_GAP = 12
const DT_MAX_CHARS = 38

function escapeDtText(text: string): string {
  return String(text || '')
    .replace(/\\/g, '\\\\')
    .replace(/'/g, '\u2019')  // right single quotation mark — avoids breaking outer ' quote at level 2
    .replace(/:/g, '\\:')
    .replace(/\[/g, '\\[')
    .replace(/\]/g, '\\]')
    .replace(/%/g, '%%')
}

function wrapDtText(text: string): string[] {
  const normalized = String(text || '').replace(/\s+/g, ' ').trim()
  if (!normalized) return []
  const words = normalized.split(' ')
  const lines: string[] = []
  let current = ''
  for (const word of words) {
    const candidate = current ? `${current} ${word}` : word
    if (candidate.length <= DT_MAX_CHARS) {
      current = candidate
    } else {
      if (current) lines.push(current)
      current = word.length > DT_MAX_CHARS ? word.slice(0, DT_MAX_CHARS) : word
    }
  }
  if (current) lines.push(current)
  return lines.slice(0, 3)
}

function buildDrawtextFilter(rows: SubtitleRow[], fontFile: string): string {
  const base = `fontfile=${fontFile}:fontsize=28:fontcolor=white:box=1:boxcolor=black@0.7:borderw=2:bordercolor=black@0.5`
  const filters: string[] = []

  const pushLines = (lines: string[], enable: string, bottomOffset: number): void => {
    for (let i = 0; i < lines.length; i += 1) {
      const distFromBottom = bottomOffset + (lines.length - 1 - i) * DT_LINE_HEIGHT
      filters.push(`drawtext=${base}:text='${escapeDtText(lines[i])}':enable=${enable}:x=(w-text_w)/2:y=h-${distFromBottom}`)
    }
  }

  for (const row of rows.slice(0, 120)) {
    const t0 = (Math.max(0, row.start_ms) / 1000).toFixed(3)
    const t1 = (Math.max(0, row.end_ms) / 1000).toFixed(3)
    const enable = `between(t\\,${t0}\\,${t1})`
    const engLines = String(row.text_eng || '').trim() ? wrapDtText(row.text_eng) : []
    const ruLines = String(row.text_ru || '').trim() ? wrapDtText(row.text_ru) : []

    if (engLines.length > 0 && ruLines.length > 0) {
      pushLines(ruLines, enable, DT_MARGIN_BOTTOM)
      pushLines(engLines, enable, DT_MARGIN_BOTTOM + ruLines.length * DT_LINE_HEIGHT + DT_BLOCK_GAP)
    } else if (ruLines.length > 0) {
      pushLines(ruLines, enable, DT_MARGIN_BOTTOM)
    } else if (engLines.length > 0) {
      pushLines(engLines, enable, DT_MARGIN_BOTTOM)
    }
  }
  return filters.join(',')
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
    const TARGET_RATE = 24000

    // Decode entire source audio into JS memory once — like Python's AudioSegment.from_file().
    // All sentence segments are sliced from this buffer; no per-sentence FFmpeg calls needed.
    progress(input.onProgress, 'Decoding source audio', 20)
    await yieldToBrowser()
    const sourceBuffer = await decodeAudioBlobToBuffer(input.sourceBlob)

    let currentMs = 0
    const outputChunks: Float32Array[] = []
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
          progress(
            input.onProgress,
            `Rendering source segment ${i + 1}/${input.sentences.length}`,
            34 + Math.round(((i + 1) / Math.max(1, input.sentences.length)) * 12),
          )
          await yieldToBrowser()
          const startSample = Math.round(sourceStartMs / 1000 * sourceBuffer.sampleRate)
          const endSample = Math.min(sourceBuffer.length, Math.round(sourceEndMs / 1000 * sourceBuffer.sampleRate))
          const rawPcm = sourceBuffer.getChannelData(0).slice(startSample, Math.max(startSample + 1, endSample))
          const sourcePcm = await resampleFloat32(rawPcm, sourceBuffer.sampleRate, TARGET_RATE)
          const durationMs = Math.max(300, Math.round(sourcePcm.length / TARGET_RATE * 1000))
          const startMs = currentMs
          const endMs = startMs + durationMs
          outputChunks.push(sourcePcm)
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
              outputChunks.push(new Float32Array(Math.round(leadSilenceMs / 1000 * TARGET_RATE)))
              currentMs += leadSilenceMs
            }
            if (flags.bilingualSimultaneous && flags.includeSource) {
              outputChunks.push(new Float32Array(Math.round(10 / 1000 * TARGET_RATE)))
              currentMs += 10
            }
            await yieldToBrowser()
            let ttsPcm: Float32Array
            let ttsText: string
            if (input.ttsProvider) {
              progress(
                input.onProgress,
                `Normalizing translated segment ${i + 1}/${input.sentences.length}`,
                46 + Math.round(((i + 1) / Math.max(1, input.sentences.length)) * 10),
              )
              const ttsBlob = await input.ttsProvider(i, textForTts)
              ttsPcm = await decodeBlobToPcm(ttsBlob, TARGET_RATE)
              ttsText = textForTts
            } else {
              const result = await synthesizeTargetSegmentPcm(textForTts, i, input.sentences.length, TARGET_RATE, input.onProgress)
              ttsPcm = result.pcm
              ttsText = result.text
            }
            const ttsStartMs = currentMs
            const ttsEndMs = ttsStartMs + Math.max(300, Math.round(ttsPcm.length / TARGET_RATE * 1000))
            outputChunks.push(ttsPcm)
            targetSubtitleSegments.push({ start_ms: ttsStartMs, end_ms: ttsEndMs, text_eng: '', text_ru: ttsText })
            window.target_start_ms = ttsStartMs
            window.target_end_ms = ttsEndMs
            if (!flags.bilingualSimultaneous) {
              bilingualSequentialSegments.push({ start_ms: ttsStartMs, end_ms: ttsEndMs, text_eng: '', text_ru: ttsText })
            }
            currentMs = ttsEndMs
          }
        }

        sentenceWindows.push(window)

        if (i < input.sentences.length - 1) {
          const nextRow = input.sentences[i + 1]
          const sourceGapMs = Math.max(
            10,
            Math.floor((Math.max(0, Number(nextRow.start_ms || 0)) - Math.max(0, Number(row.end_ms || 0))) / 3),
          )
          outputChunks.push(new Float32Array(Math.round(sourceGapMs / 1000 * TARGET_RATE)))
          currentMs += sourceGapMs
        }
      }

      if (!outputChunks.length) {
        throw new Error('No media segments were generated.')
      }

      // Concatenate all PCM chunks in JS memory — like Python's out.export(mp3_out).
      progress(input.onProgress, 'Assembling audio track', 57)
      await yieldToBrowser()
      const totalSamples = outputChunks.reduce((s, c) => s + c.length, 0)
      const outputPcm = new Float32Array(totalSamples)
      let pcmOffset = 0
      for (const chunk of outputChunks) {
        outputPcm.set(chunk, pcmOffset)
        pcmOffset += chunk.length
      }
      // Release per-sentence PCM buffers — no longer needed after assembly
      outputChunks.length = 0

      // Encode assembled PCM → MP3. Split into ≤40MB WAV chunks to avoid WASM heap OOM
      // on long files. MP3 frames are self-contained so chunks can be concatenated directly.
      progress(input.onProgress, 'Encoding audio track', 60)
      await yieldToBrowser()
      const MAX_CHUNK_SAMPLES = Math.floor(40 * 1024 * 1024 / 2) // 40MB WAV = 20M s16 samples
      const mp3Parts: Uint8Array[] = []
      for (let ci = 0, off = 0; off < outputPcm.length; ci++, off += MAX_CHUNK_SAMPLES) {
        const slice = outputPcm.subarray(off, Math.min(off + MAX_CHUNK_SAMPLES, outputPcm.length))
        const chunkWav = rawAudioToWavBlob(slice, TARGET_RATE)
        const chunkIn = `ac_${ci}.wav`
        const chunkOut = `ac_${ci}.mp3`
        await ffmpeg.writeFile(chunkIn, await util.fetchFile(chunkWav))
        await runCommand(ffmpeg, ['-y', '-i', chunkIn, '-ac', '1', '-ar', String(TARGET_RATE), '-c:a', 'libmp3lame', '-q:a', '2', chunkOut], 'Audio encoding')
        await safeDelete(ffmpeg, chunkIn)
        const raw = await ffmpeg.readFile(chunkOut) as Uint8Array
        mp3Parts.push(new Uint8Array(raw.buffer, raw.byteOffset, raw.byteLength))
        await safeDelete(ffmpeg, chunkOut)
      }
      // Concatenate MP3 parts and write final file
      const totalMp3 = mp3Parts.reduce((s, p) => s + p.byteLength, 0)
      const mp3Combined = new Uint8Array(totalMp3)
      let mp3Off = 0
      for (const part of mp3Parts) { mp3Combined.set(part, mp3Off); mp3Off += part.byteLength }
      mp3Parts.length = 0 // release encoded chunk buffers
      await ffmpeg.writeFile(audioFile, mp3Combined)
      // Yield after audio encoding to allow GC of large PCM/MP3 buffers before video composition
      await yieldToBrowser()
      await yieldToBrowser()

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

      // For video sources write the source file to WASM FS now (needed for video track extraction).
      // For audio sources it is never written — saves ~5MB of WASM heap during the audio loop.
      if (input.sourceKind === 'video') {
        await ffmpeg.writeFile(sourceFile, await util.fetchFile(input.sourceBlob))
      }

      progress(input.onProgress, 'Composing video track', 74)
      await yieldToBrowser()
      // subtitles filter (libass) uses a single filter instance reading the SRT file — avoids
      // the ~360MB heap cost of 700+ drawtext instances each loading the font independently.
      const vfArgs = ffmpegFontLoaded
        ? ['-vf', `subtitles=${subtitleFile}:fontsdir=/:force_style='FontName=DejaVu Sans,FontSize=22,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=2,Shadow=0,MarginV=30'`]
        : []
      console.log('[Render] subtitle filter:', vfArgs.length ? 'enabled (libass)' : 'disabled (no font)')
      const videoArgs = input.sourceKind === 'video'
        ? [
            '-y',
            '-i', sourceFile,
            '-i', audioFile,
            ...vfArgs,
            '-map', '0:v',
            '-map', '1:a',
            '-c:v', 'libx264',
            '-pix_fmt', 'yuv420p',
            '-preset', 'ultrafast',
            '-crf', '23',
            '-c:a', 'aac',
            '-b:a', '192k',
            '-shortest',
            '-movflags', '+faststart',
            videoFile,
          ]
        : [
            '-y',
            '-f', 'lavfi',
            '-i', 'color=c=black:size=640x360:rate=5',
            '-i', audioFile,
            ...vfArgs,
            '-shortest',
            '-c:v', 'libx264',
            '-pix_fmt', 'yuv420p',
            '-preset', 'ultrafast',
            '-tune', 'stillimage',
            '-crf', '28',
            '-c:a', 'aac',
            '-b:a', '128k',
            videoFile,
          ]
      await runWithProgressPulse(
        runCommand(ffmpeg, videoArgs, 'Video composition'),
        input.onProgress,
        'Composing video track',
        74,
        95,
        1200,
      )
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
import { configureTransformersEnv } from './transformersEnv'
import { recordRuntimeDiagnostic } from './runtimeDiagnostics'
import dejaVuSansUrl from '../assets/DejaVuSans.ttf?url'
