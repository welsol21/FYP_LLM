/**
 * Translation WebWorker — runs Xenova/opus-mt-en-ru in a background thread.
 *
 * Message protocol (main → worker):
 *   { type: 'translate', id: string, sentences: string[] }
 *
 * Message protocol (worker → main):
 *   { type: 'progress', loaded: number, total: number }
 *   { type: 'result', id: string, index: number, total: number, text: string }
 *   { type: 'done', id: string }
 *   { type: 'error', id: string, message: string }
 */

/* eslint-disable @typescript-eslint/no-explicit-any */
import { pipeline, env } from '@huggingface/transformers'

// Models are served locally — no CDN downloads allowed.
;(env as any).allowLocalModels = true
;(env as any).allowRemoteModels = false
;(env as any).localModelPath = '/models/'

// ONNX Runtime WASM files served locally from /onnx/ — enables multi-threaded
// CPU inference (SharedArrayBuffer) without CDN dependency.
;(env as any).backends.onnx.wasm.wasmPaths = '/onnx/'

let translator: any = null

async function getTranslator(): Promise<any> {
  if (translator) return translator

  const progressCb = (info: any) => {
    if (info?.status === 'initiate') {
      self.postMessage({ type: 'progress', loaded: 0, total: 100 })
    } else if (typeof info?.progress === 'number') {
      self.postMessage({ type: 'progress', loaded: Math.round(info.progress as number), total: 100 })
    }
  }

  const tryLoad = async (device: string, dtype: string) => {
    console.log('[Translation] trying device:', device, 'dtype:', dtype)
    return await (pipeline as any)('translation', 'Xenova/opus-mt-en-ru', {
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
      translator = await tryLoad('webgpu', 'fp32')
    } catch (e) {
      console.warn('[Translation] WebGPU failed, falling back to WASM q8:', e)
      translator = await tryLoad('wasm', 'q8')
    }
  } else {
    console.log('[Translation] No WebGPU adapter, using WASM q8')
    translator = await tryLoad('wasm', 'q8')
  }

  return translator
}

self.addEventListener('message', async (event: MessageEvent) => {
  const { type, id, sentences } = event.data as { type: string; id: string; sentences: string[] }
  if (type !== 'translate') return
  try {
    const t = await getTranslator()
    const total = sentences.length
    for (let index = 0; index < total; index += 1) {
      const sentence = sentences[index]
      const output: any = await t(sentence, { clean_up_tokenization_spaces: true })
      const rawText = String(
        (Array.isArray(output) ? (output[0] as any)?.translation_text : '') || '',
      ).trim()
      // Sentencepiece sometimes outputs "П р и в е т" — collapse if every token is 1 char
      const words = rawText.split(' ')
      const text = words.length > 1 && words.every((w: string) => w.length <= 1)
        ? words.join('')
        : rawText
      self.postMessage({ type: 'result', id, index, total, text })
    }
    self.postMessage({ type: 'done', id })
  } catch (err) {
    self.postMessage({ type: 'error', id, message: err instanceof Error ? err.message : String(err) })
  }
})
