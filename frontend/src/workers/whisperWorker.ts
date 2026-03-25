/**
 * Whisper WebWorker — runs Xenova/whisper-small.en in a background thread.
 *
 * Message protocol (main → worker):
 *   { type: 'transcribe', id: string, audio: Float32Array, sampling_rate: number }
 *
 * Message protocol (worker → main):
 *   { type: 'progress', id: string, message: string }
 *   { type: 'done', id: string, fullText: string, sentences: Array<{text, start_sec, end_sec}> }
 *   { type: 'error', id: string, message: string }
 */

/* eslint-disable @typescript-eslint/no-explicit-any */
import { pipeline, env } from '@huggingface/transformers'

;(env as any).allowLocalModels = false

const MODEL = (import.meta as any).env?.VITE_WHISPER_MODEL || 'Xenova/whisper-base.en'

let transcriber: any = null

async function getTranscriber(onProgress: (msg: string) => void): Promise<any> {
  if (transcriber) return transcriber

  // Aggregate per-file progress into one smooth overall percentage
  const fileProgress: Record<string, number> = {}
  const progressCb = (info: any) => {
    if (!info?.file) return
    if (info.status === 'progress' && typeof info.progress === 'number') {
      fileProgress[info.file] = info.progress
    } else if (info.status === 'done') {
      fileProgress[info.file] = 100
    } else if (info.status === 'initiate') {
      fileProgress[info.file] = 0
    }
    const files = Object.values(fileProgress)
    if (files.length === 0) return
    const avg = Math.round(files.reduce((s, v) => s + v, 0) / files.length)
    onProgress(`Loading Whisper model (${avg}%)…`)
  }

  const tryLoad = async (device: string, dtype: string) => {
    console.log('[Whisper] trying device:', device, 'dtype:', dtype)
    return await (pipeline as any)('automatic-speech-recognition', MODEL, {
      device,
      dtype,
      progress_callback: progressCb,
    })
  }

  // Check WebGPU adapter availability BEFORE trying to load — failed WebGPU
  // attempts corrupt ONNX Runtime state, causing even the WASM fallback to fail.
  let gpuAdapter: any = null
  if (typeof navigator !== 'undefined' && 'gpu' in navigator) {
    try {
      gpuAdapter = await (navigator as any).gpu.requestAdapter()
    } catch { /* WebGPU not available */ }
  }

  if (gpuAdapter) {
    try {
      transcriber = await tryLoad('webgpu', 'fp32')
    } catch (e) {
      console.warn('[Whisper] WebGPU failed, falling back to WASM q8:', e)
      transcriber = await tryLoad('wasm', 'q8')
    }
  } else {
    console.log('[Whisper] No WebGPU adapter, using WASM q8')
    transcriber = await tryLoad('wasm', 'q8')
  }

  return transcriber
}

function groupChunksToSentences(
  chunks: Array<{ text: string; timestamp: [number | null, number | null] }>,
): Array<{ text: string; start_sec: number; end_sec: number }> {
  const sentences: Array<{ text: string; start_sec: number; end_sec: number }> = []
  let buf = ''
  let start: number | null = null
  let end = 0

  for (const chunk of chunks) {
    const text = String(chunk.text || '').trim()
    if (!text) continue
    if (start === null) start = chunk.timestamp[0] ?? 0
    end = chunk.timestamp[1] ?? end
    buf += (buf ? ' ' : '') + text
    if (/[.!?](\s|$)/.test(buf)) {
      sentences.push({ text: buf.trim(), start_sec: start ?? 0, end_sec: end })
      buf = ''
      start = null
    }
  }
  if (buf.trim() && start !== null) {
    sentences.push({ text: buf.trim(), start_sec: start, end_sec: end })
  }
  return sentences
}

self.addEventListener('message', async (event: MessageEvent) => {
  const { type, id, audio, sampling_rate } = event.data as {
    type: string
    id: string
    audio: Float32Array
    sampling_rate: number
  }
  if (type !== 'transcribe') return
  console.log('[Whisper] received transcribe, audio length:', audio?.length, 'sr:', sampling_rate)
  try {
    const t = await getTranscriber((msg) => self.postMessage({ type: 'progress', id, message: msg }))
    console.log('[Whisper] model ready, starting inference')
    // Pre-calculate total chunks so we can show a real percentage.
    // window=30s stride=5s → jump=20s → totalChunks ≈ ceil(duration / 20)
    const CHUNK_S = 30, STRIDE_S = 5
    const jump = (CHUNK_S - 2 * STRIDE_S) * sampling_rate
    const totalChunks = Math.max(1, Math.ceil(audio.length / jump))
    self.postMessage({ type: 'progress', id, message: 'Transcribing…', pct: 0 })
    let chunksProcessed = 0
    let currentPct = 0
    let tokensSinceChunk = 0
    // Pass a plain Float32Array (already 16 kHz from main thread).
    // Transformers.js prepareAudios() only handles string|URL|Float32Array|Float64Array —
    // passing { array, sampling_rate } causes Ze.subarray errors in _call_whisper chunking.
    // whisper-small.en is English-only: do NOT pass language/task (causes error)
    const result: any = await t(audio, {
      return_timestamps: true,
      chunk_length_s: CHUNK_S,
      stride_length_s: STRIDE_S,
      // Fires after each generated token — keeps UI alive during long single-chunk inference
      callback_function: (_: any) => {
        tokensSinceChunk++
        // Throttle to every 8 tokens to avoid flooding postMessage
        if (tokensSinceChunk % 8 === 0) {
          const dots = '.'.repeat((Math.floor(tokensSinceChunk / 8) % 3) + 1)
          self.postMessage({ type: 'progress', id, message: `Transcribing${dots} ${currentPct}%`, pct: currentPct })
        }
      },
      chunk_callback: (_chunk: any) => {
        chunksProcessed++
        tokensSinceChunk = 0
        currentPct = Math.min(99, Math.round((chunksProcessed / totalChunks) * 100))
        console.log('[Whisper] chunk', chunksProcessed, '/', totalChunks, `(${currentPct}%)`)
        self.postMessage({ type: 'progress', id, message: `Transcribing… ${currentPct}%`, pct: currentPct })
      },
    })
    console.log('[Whisper] inference done, chunks:', result.chunks?.length)
    const sentences = groupChunksToSentences(result.chunks ?? [])
    self.postMessage({ type: 'done', id, fullText: String(result.text || ''), sentences })
  } catch (err) {
    console.error('[Whisper] error:', err)
    self.postMessage({ type: 'error', id, message: err instanceof Error ? err.message : String(err) })
  }
})
