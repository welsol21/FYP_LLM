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

const MODEL = (import.meta as any).env?.VITE_WHISPER_MODEL || 'Xenova/whisper-small.en'

let transcriber: any = null

async function getTranscriber(onProgress: (msg: string) => void): Promise<any> {
  if (transcriber) return transcriber
  transcriber = await (pipeline as any)('automatic-speech-recognition', MODEL, {
    dtype: 'q8',
    progress_callback: (info: any) => {
      if (typeof info?.progress === 'number' && info.status === 'progress') {
        onProgress(`Loading Whisper model (${Math.round(info.progress as number)}%)…`)
      }
    },
  })
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
  try {
    const t = await getTranscriber((msg) => self.postMessage({ type: 'progress', id, message: msg }))
    self.postMessage({ type: 'progress', id, message: 'Transcribing audio…' })
    const result: any = await t({ array: audio, sampling_rate }, {
      return_timestamps: true,
      chunk_length_s: 30,
      stride_length_s: 5,
      language: 'english',
      task: 'transcribe',
    })
    const sentences = groupChunksToSentences(result.chunks ?? [])
    self.postMessage({ type: 'done', id, fullText: String(result.text || ''), sentences })
  } catch (err) {
    self.postMessage({ type: 'error', id, message: err instanceof Error ? err.message : String(err) })
  }
})
