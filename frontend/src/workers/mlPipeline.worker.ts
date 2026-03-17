// ML Pipeline Web Worker
// Runs transformers.js pipelines in a dedicated thread to keep the UI responsive.
// No SharedArrayBuffer required — numThreads=1.
//
// Static imports only: Vite bundles classic workers as IIFE, which does not
// support code-splitting (dynamic import()). All dependencies must be imported
// at the top level.

import { pipeline, env, VitsModel, VitsTokenizer, TextToAudioPipeline } from '@huggingface/transformers'

type WorkerRequest =
  | { id: string; type: 'ASR'; audioData: Float32Array; sampleRate: number; modelPath: string }
  | { id: string; type: 'TRANSLATE'; sentences: string[]; modelPath: string }
  | { id: string; type: 'TTS'; sentences: string[]; modelPath: string }

type WorkerResponse =
  | { id: string; type: 'PROGRESS'; message: string; progress: number }
  | { id: string; type: 'RESULT'; payload: unknown }
  | { id: string; type: 'ERROR'; message: string }

// ---------------------------------------------------------------------------
// Pipeline caches
// ---------------------------------------------------------------------------

type AsrPipeline = (audio: Float32Array, options?: Record<string, unknown>) => Promise<unknown>
type TranslationPipeline = (input: string, options?: Record<string, unknown>) => Promise<unknown>
type TtsPipelineOutput = { audio: Float32Array; sampling_rate: number }
type TtsPipeline = (text: string, options?: Record<string, unknown>) => Promise<TtsPipelineOutput>

let asrPipelinePromise: Promise<AsrPipeline> | null = null
let translationPipelinePromise: Promise<TranslationPipeline> | null = null
let ttsPipelinePromise: Promise<TtsPipeline> | null = null

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function send(response: WorkerResponse): void {
  self.postMessage(response)
}

function sendProgress(id: string, message: string, progress: number): void {
  send({ id, type: 'PROGRESS', message, progress: Math.max(0, Math.min(100, Math.round(progress))) })
}

function sendResult(id: string, payload: unknown): void {
  send({ id, type: 'RESULT', payload })
}

function sendError(id: string, message: string): void {
  send({ id, type: 'ERROR', message })
}

// ---------------------------------------------------------------------------
// transformers.js environment setup — mirrors configureTransformersEnvForMode
// but runs inside the worker context.
// ---------------------------------------------------------------------------

let envConfigured = false

async function ensureEnvConfigured(): Promise<void> {
  if (envConfigured) return
  envConfigured = true

  const record = env as unknown as Record<string, unknown>
  record.allowLocalModels = true
  record.allowRemoteModels = false
  record.useBrowserCache = false // workers don't have Cache API in WebKitGTK

  // Patch the ONNX JSEP .mjs blob URL (same logic as patchOnnxJsepBlobUrl in
  // transformersEnv.ts, but runs in worker context where location.href is also
  // a tauri://localhost/ URL).
  const backends = record.backends as Record<string, unknown> | undefined
  const onnx = backends?.onnx as Record<string, unknown> | undefined
  const wasm = onnx?.wasm as Record<string, unknown> | undefined
  if (wasm && typeof wasm === 'object') {
    try {
      const mjsUrl = new URL('/assets/ort-wasm-simd-threaded.jsep.mjs', self.location.href).href
      let text = await fetch(mjsUrl).then((r) => {
        if (!r.ok) throw new Error(`fetch ${mjsUrl}: ${r.status}`)
        return r.text()
      })
      const wasmUrl = new URL('/assets/ort-wasm-simd-threaded.jsep.wasm', self.location.href).href
      text = text.replace(/"ort-wasm-simd-threaded\.jsep\.wasm"/g, JSON.stringify(wasmUrl))
      text = text.replace(/'ort-wasm-simd-threaded\.jsep\.wasm'/g, JSON.stringify(wasmUrl))
      const blobUrl = URL.createObjectURL(new Blob([text], { type: 'text/javascript' }))
      const existing = wasm.wasmPaths
      const merged = (existing && typeof existing === 'object')
        ? { ...(existing as Record<string, unknown>), mjs: blobUrl }
        : { mjs: blobUrl }
      Object.defineProperty(wasm, 'wasmPaths', {
        value: merged,
        writable: true,
        configurable: true,
        enumerable: true,
      })
    } catch {
      // Non-fatal: JSEP may still work without the blob URL patch in some builds
    }
  }
}

// ---------------------------------------------------------------------------
// ASR handler
// ---------------------------------------------------------------------------

async function getAsrPipeline(modelPath: string, id: string): Promise<AsrPipeline> {
  if (!asrPipelinePromise) {
    asrPipelinePromise = (async () => {
      sendProgress(id, 'Loading local ASR model', 24)
      const startedAt = Date.now()
      const heartbeat = setInterval(() => {
        const elapsedSec = Math.max(1, Math.floor((Date.now() - startedAt) / 1000))
        sendProgress(id, `Loading local ASR model (${elapsedSec}s)`, 24)
      }, 3000)
      try {
        await ensureEnvConfigured()
        const record = env as unknown as Record<string, unknown>
        const modelsRoot = modelPath.replace(/\/[^/]+\/?$/, '')
        record.localModelPath = modelsRoot
        const modelId = modelPath.split('/').pop() || 'whisper-base.en'
        const pipe = await pipeline('automatic-speech-recognition', modelId, {
          quantized: true,
          local_files_only: true,
        } as Record<string, unknown>)
        sendProgress(id, 'ASR model loaded', 46)
        return pipe as unknown as AsrPipeline
      } finally {
        clearInterval(heartbeat)
      }
    })()
  }
  return asrPipelinePromise
}

async function handleAsr(req: Extract<WorkerRequest, { type: 'ASR' }>): Promise<void> {
  const { id, audioData, modelPath } = req
  try {
    const asr = await getAsrPipeline(modelPath, id)
    sendProgress(id, 'Running local ASR', 62)
    const result = await asr(audioData, {
      chunk_length_s: 30,
      stride_length_s: 5,
      return_timestamps: 'word',
    })
    sendProgress(id, 'ASR completed', 100)
    sendResult(id, result)
  } catch (err) {
    asrPipelinePromise = null // reset so next call can retry
    sendError(id, err instanceof Error ? err.message : String(err))
  }
}

// ---------------------------------------------------------------------------
// Translation handler
// ---------------------------------------------------------------------------

async function getTranslationPipeline(modelPath: string, id: string): Promise<TranslationPipeline> {
  if (!translationPipelinePromise) {
    translationPipelinePromise = (async () => {
      sendProgress(id, 'Loading local translation model', 20)
      const startedAt = Date.now()
      const heartbeat = setInterval(() => {
        const elapsedSec = Math.max(1, Math.floor((Date.now() - startedAt) / 1000))
        sendProgress(id, `Loading local translation model (${elapsedSec}s)`, 20)
      }, 3000)
      try {
        await ensureEnvConfigured()
        const record = env as unknown as Record<string, unknown>
        const modelsRoot = modelPath.replace(/\/[^/]+\/?$/, '')
        record.localModelPath = modelsRoot
        const modelId = modelPath.split('/').pop() || 'm2m100_418M'
        const pipe = await pipeline('translation', modelId, { quantized: true, local_files_only: true } as Record<string, unknown>)
        sendProgress(id, 'Translation model loaded', 40)
        return pipe as unknown as TranslationPipeline
      } finally {
        clearInterval(heartbeat)
      }
    })()
  }
  return translationPipelinePromise
}

async function handleTranslate(req: Extract<WorkerRequest, { type: 'TRANSLATE' }>): Promise<void> {
  const { id, sentences, modelPath } = req
  try {
    const pipe = await getTranslationPipeline(modelPath, id)
    sendProgress(id, 'Translation model ready', 40)
    const out: string[] = []
    for (let i = 0; i < sentences.length; i += 1) {
      const result = await pipe(sentences[i], { src_lang: 'en', tgt_lang: 'ru', max_length: 256 })
      const translated = parseTranslationText(result)
      if (!translated) throw new Error(`Translation model returned empty output for sentence ${i + 1}.`)
      out.push(translated)
      sendProgress(id, `Translating ${i + 1}/${sentences.length}`, 40 + Math.round(((i + 1) / sentences.length) * 60))
    }
    sendResult(id, out)
  } catch (err) {
    translationPipelinePromise = null
    sendError(id, err instanceof Error ? err.message : String(err))
  }
}

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

// ---------------------------------------------------------------------------
// TTS handler
// ---------------------------------------------------------------------------

async function getTtsPipeline(modelPath: string, id: string): Promise<TtsPipeline> {
  if (!ttsPipelinePromise) {
    ttsPipelinePromise = (async () => {
      sendProgress(id, 'Loading local TTS model', 22)
      const startedAt = Date.now()
      const heartbeat = setInterval(() => {
        const elapsedSec = Math.max(1, Math.floor((Date.now() - startedAt) / 1000))
        sendProgress(id, `Loading local TTS model (${elapsedSec}s)`, 22)
      }, 3000)
      try {
        await ensureEnvConfigured()
        const record = env as unknown as Record<string, unknown>
        const modelsRoot = modelPath.replace(/\/[^/]+\/?$/, '')
        record.localModelPath = modelsRoot
        const modelId = modelPath.split('/').pop() || 'mms-tts-rus'
        const opts = { quantized: true, local_files_only: true } as Record<string, unknown>
        // Load VitsModel and VitsTokenizer directly to bypass AutoProcessor.
        // MMS-TTS (VitsModel) has no preprocessor_config.json and does not need
        // a processor — TextToAudioPipeline routes to _call_text_to_waveform when
        // processor is null, which is the correct path for VITS models.
        const [model, tokenizer] = await Promise.all([
          VitsModel.from_pretrained(modelId, opts),
          VitsTokenizer.from_pretrained(modelId, { local_files_only: true } as Record<string, unknown>),
        ])
        const tts = new TextToAudioPipeline({
          task: 'text-to-audio',
          model: model as unknown as ConstructorParameters<typeof TextToAudioPipeline>[0]['model'],
          tokenizer: tokenizer as unknown as ConstructorParameters<typeof TextToAudioPipeline>[0]['tokenizer'],
          processor: null as unknown as ConstructorParameters<typeof TextToAudioPipeline>[0]['processor'],
        })
        sendProgress(id, 'Local TTS model loaded', 30)
        return tts as unknown as TtsPipeline
      } finally {
        clearInterval(heartbeat)
      }
    })()
  }
  return ttsPipelinePromise
}

async function handleTts(req: Extract<WorkerRequest, { type: 'TTS' }>): Promise<void> {
  const { id, sentences, modelPath } = req
  try {
    const tts = await getTtsPipeline(modelPath, id)
    const results: { audio: Float32Array; sampling_rate: number }[] = []
    for (let i = 0; i < sentences.length; i += 1) {
      sendProgress(id, `Synthesizing speech ${i + 1}/${sentences.length}`, 30 + Math.round(((i + 1) / Math.max(1, sentences.length)) * 24))
      const raw = await tts(sentences[i])
      const sampleRate = Number(raw?.sampling_rate || 16000)
      const samples = raw?.audio instanceof Float32Array ? raw.audio : new Float32Array(0)
      if (!samples.length) throw new Error(`TTS returned empty audio for sentence ${i + 1}.`)
      results.push({ audio: samples, sampling_rate: sampleRate })
    }
    // Transfer the audio ArrayBuffers to avoid copying large float arrays.
    const transfers = results.map((r) => r.audio.buffer as ArrayBuffer)
    ;(self as unknown as { postMessage(msg: unknown, transfer: Transferable[]): void })
      .postMessage({ id, type: 'RESULT', payload: results } satisfies WorkerResponse, transfers)
  } catch (err) {
    ttsPipelinePromise = null
    sendError(id, err instanceof Error ? err.message : String(err))
  }
}

// ---------------------------------------------------------------------------
// Message dispatcher
// ---------------------------------------------------------------------------

self.onmessage = (event: MessageEvent<WorkerRequest>): void => {
  const req = event.data
  if (!req || typeof req !== 'object' || !req.type) return
  switch (req.type) {
    case 'ASR':
      void handleAsr(req)
      break
    case 'TRANSLATE':
      void handleTranslate(req)
      break
    case 'TTS':
      void handleTts(req)
      break
    default:
      // Unknown request type — ignore
      break
  }
}
