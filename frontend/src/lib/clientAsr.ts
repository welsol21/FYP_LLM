type AsrProgressPayload = {
  message: string
  progress: number
}

type AsrOptions = {
  onProgress?: (payload: AsrProgressPayload) => void
}

type AsrPipeline = (audio: Float32Array, options?: Record<string, unknown>) => Promise<unknown>

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
      const transformers = await import('@huggingface/transformers')
      const env = (transformers as unknown as { env?: Record<string, unknown> }).env
      if (env && typeof env === 'object') {
        ;(env as Record<string, unknown>).allowLocalModels = false
        ;(env as Record<string, unknown>).allowRemoteModels = true
        ;(env as Record<string, unknown>).useBrowserCache = true
      }
      const modelId = String(import.meta.env?.VITE_CLIENT_ASR_MODEL || 'Xenova/whisper-base.en').trim()
      const pipelineFactory = (transformers as unknown as {
        pipeline: (task: string, model: string, opts?: Record<string, unknown>) => Promise<AsrPipeline>
      }).pipeline
      const pipe = await pipelineFactory('automatic-speech-recognition', modelId, {
        quantized: true,
      })
      notify(options, 'ASR model loaded', 46)
      return pipe
    })()
  }
  return pipelinePromise
}

export async function transcribeMediaBlob(blob: Blob, options?: AsrOptions): Promise<string> {
  const mono16k = await decodeTo16kMono(blob, options)
  const asr = await getAsrPipeline(options)
  notify(options, 'Running local ASR', 62)
  const result = await asr(mono16k, {
    chunk_length_s: 30,
    stride_length_s: 5,
  })
  notify(options, 'ASR completed', 100)
  if (typeof result === 'string') return result.trim()
  if (result && typeof result === 'object' && 'text' in result) {
    return String((result as { text?: string }).text || '').trim()
  }
  return ''
}

