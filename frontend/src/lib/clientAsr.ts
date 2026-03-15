import { resolveDesktopRuntimeAssetUrl } from './desktopRuntime'
import { recordRuntimeDiagnostic } from './runtimeDiagnostics'
import { configureTransformersEnvForMode } from './transformersEnv'

type AsrProgressPayload = {
  message: string
  progress: number
}

type AsrOptions = {
  onProgress?: (payload: AsrProgressPayload) => void
}

type AsrPipeline = (audio: Float32Array, options?: Record<string, unknown>) => Promise<unknown>

export type TimedSentence = {
  text: string
  start_ms: number
  end_ms: number
}

export type DetailedAsrResult = {
  text: string
  sentences: TimedSentence[]
}

let pipelinePromise: Promise<AsrPipeline> | null = null

function notify(options: AsrOptions | undefined, message: string, progress: number): void {
  options?.onProgress?.({
    message,
    progress: Math.max(0, Math.min(100, Math.round(progress))),
  })
}

function monoFromAudioBuffer(buffer: AudioBuffer): Float32Array {
  const channels = buffer.numberOfChannels
  if (channels <= 1) {
    return buffer.getChannelData(0).slice()
  }
  const length = buffer.length
  const out = new Float32Array(length)
  for (let channel = 0; channel < channels; channel += 1) {
    const data = buffer.getChannelData(channel)
    for (let i = 0; i < length; i += 1) out[i] += data[i]
  }
  for (let i = 0; i < length; i += 1) out[i] /= channels
  return out
}

function resampleLinear(input: Float32Array, srcRate: number, targetRate: number): Float32Array {
  if (!input.length || srcRate === targetRate) return input
  const targetLength = Math.max(1, Math.round((input.length * targetRate) / srcRate))
  const out = new Float32Array(targetLength)
  const ratio = srcRate / targetRate
  for (let i = 0; i < targetLength; i += 1) {
    const srcPos = i * ratio
    const left = Math.floor(srcPos)
    const right = Math.min(left + 1, input.length - 1)
    const frac = srcPos - left
    out[i] = input[left] * (1 - frac) + input[right] * frac
  }
  return out
}

async function decodeTo16kMono(blob: Blob, options?: AsrOptions): Promise<Float32Array> {
  notify(options, 'Decoding media audio', 8)
  const buffer = typeof (blob as Blob & { arrayBuffer?: () => Promise<ArrayBuffer> }).arrayBuffer === 'function'
    ? await (blob as Blob & { arrayBuffer: () => Promise<ArrayBuffer> }).arrayBuffer()
    : await new Response(blob).arrayBuffer()
  const Ctx = (globalThis as typeof globalThis & { webkitAudioContext?: typeof AudioContext }).AudioContext
    || (globalThis as typeof globalThis & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
  if (!Ctx) throw new Error('WebAudio is unavailable in this browser.')
  const ctx = new Ctx()
  try {
    const decoded = await ctx.decodeAudioData(buffer.slice(0))
    const mono = monoFromAudioBuffer(decoded)
    const resampled = resampleLinear(mono, decoded.sampleRate, 16000)
    notify(options, 'Audio prepared for ASR', 18)
    return resampled
  } finally {
    await ctx.close().catch(() => undefined)
  }
}

async function getAsrPipeline(options?: AsrOptions): Promise<AsrPipeline> {
  if (!pipelinePromise) {
    pipelinePromise = (async () => {
      notify(options, 'Loading local ASR model', 24)
      const startedAt = Date.now()
      const heartbeat = window.setInterval(() => {
        const elapsedSec = Math.max(1, Math.floor((Date.now() - startedAt) / 1000))
        notify(options, `Loading local ASR model (${elapsedSec}s)`, 24)
      }, 3000)
      try {
        const transformers = await import('@huggingface/transformers')
        const env = (transformers as unknown as { env?: Record<string, unknown> }).env
        configureTransformersEnvForMode(env, 'desktop')
        const modelsRoot = await resolveDesktopRuntimeAssetUrl('modelsRoot')
        const modelId = 'whisper-base.en'
        if (env && typeof env === 'object') {
          ;(env as Record<string, unknown>).localModelPath = modelsRoot
        }
        recordRuntimeDiagnostic('desktop.asr', 'model.path', { modelsRoot, modelId })
        const pipelineFactory = (transformers as unknown as {
          pipeline: (task: string, model: string, opts?: Record<string, unknown>) => Promise<AsrPipeline>
        }).pipeline
        const pipe = await pipelineFactory('automatic-speech-recognition', modelId, {
          quantized: true,
          local_files_only: true,
        })
        notify(options, 'ASR model loaded', 46)
        return pipe
      } finally {
        window.clearInterval(heartbeat)
      }
    })()
  }
  return pipelinePromise
}

export async function prewarmLocalAsr(options?: AsrOptions): Promise<void> {
  await getAsrPipeline(options)
}

function chunkText(value: unknown): string {
  return String(value || '').replace(/\s+/g, ' ').trim()
}

function isSentenceEnd(text: string): boolean {
  return /[.!?]["')\]]*$/.test(String(text || '').trim())
}

function buildTimedSentencesFromResult(result: unknown): TimedSentence[] {
  const chunks = Array.isArray((result as { chunks?: unknown[] } | null | undefined)?.chunks)
    ? ((result as { chunks?: unknown[] }).chunks as unknown[])
    : []
  if (!chunks.length) return []

  const out: TimedSentence[] = []
  let parts: string[] = []
  let startMs: number | null = null
  let endMs: number | null = null

  const flush = (): void => {
    const text = parts.join(' ').replace(/\s+/g, ' ').trim()
    if (!text || startMs == null || endMs == null || endMs <= startMs) {
      parts = []
      startMs = null
      endMs = null
      return
    }
    out.push({ text, start_ms: startMs, end_ms: endMs })
    parts = []
    startMs = null
    endMs = null
  }

  for (const raw of chunks) {
    const row = (raw || {}) as { text?: unknown; timestamp?: unknown }
    const text = chunkText(row.text)
    const timestamp = Array.isArray(row.timestamp) ? row.timestamp : []
    const startSec = typeof timestamp[0] === 'number' ? Number(timestamp[0]) : null
    const endSec = typeof timestamp[1] === 'number' ? Number(timestamp[1]) : null
    if (!text || startSec == null || endSec == null) continue

    if (startMs == null) startMs = Math.max(0, Math.round(startSec * 1000))
    endMs = Math.max(startMs, Math.round(endSec * 1000))
    parts.push(text)

    if (isSentenceEnd(text)) flush()
  }

  flush()
  return out
}

export async function transcribeMediaBlobDetailed(blob: Blob, options?: AsrOptions): Promise<DetailedAsrResult> {
  const mono16k = await decodeTo16kMono(blob, options)
  const asr = await getAsrPipeline(options)
  notify(options, 'Running local ASR', 62)
  const result = await asr(mono16k, {
    chunk_length_s: 30,
    stride_length_s: 5,
    return_timestamps: 'word',
  })
  notify(options, 'ASR completed', 100)
  if (typeof result === 'string') {
    return { text: result.trim(), sentences: [] }
  }
  if (result && typeof result === 'object' && 'text' in result) {
    return {
      text: String((result as { text?: string }).text || '').trim(),
      sentences: buildTimedSentencesFromResult(result),
    }
  }
  return { text: '', sentences: [] }
}

export async function transcribeMediaBlob(blob: Blob, options?: AsrOptions): Promise<string> {
  const result = await transcribeMediaBlobDetailed(blob, options)
  return result.text
}
