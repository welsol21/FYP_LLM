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
import { pipeline, env, TextStreamer } from '@huggingface/transformers'

// Models are served locally — no CDN downloads allowed.
// If local files are missing, the user must install the PWA.
;(env as any).allowLocalModels = true
;(env as any).allowRemoteModels = false
;(env as any).localModelPath = '/models/'

// ONNX Runtime WASM files served locally from /onnx/ — enables multi-threaded
// CPU inference (SharedArrayBuffer) without CDN dependency.
;(env as any).backends.onnx.wasm.wasmPaths = '/onnx/'

const MODEL = (import.meta as any).env?.VITE_WHISPER_MODEL || 'Xenova/whisper-base.en'

let transcriber: any = null

async function getTranscriber(onProgress: (msg: string) => void): Promise<any> {
  if (transcriber) return transcriber

  const progressCb = (info: any) => {
    if (info?.status === 'initiate') onProgress('Loading Whisper model…')
  }

  const tryLoad = async (device: string, dtype: string) => {
    console.log('[Whisper] trying device:', device, 'dtype:', dtype)
    return await (pipeline as any)('automatic-speech-recognition', MODEL, {
      device,
      dtype,
      progress_callback: progressCb,
    })
  }

  transcriber = await tryLoad('wasm', 'q8')

  return transcriber
}

// Known title abbreviations that should NOT trigger a sentence flush.
const ABBREVS = new Set(['Mr', 'Mrs', 'Dr', 'Ms', 'Prof', 'Sr', 'Jr', 'St', 'vs', 'No'])

/**
 * Groups word-level Whisper chunks into sentences.
 *
 * With return_timestamps:"word" each chunk is a single word with its own
 * precise timestamp — matching the reference transcribe_and_translate_windows.py
 * algorithm (word_timestamps=True → group_units_by_sentence).
 *
 * start_sec = timestamp of the first word in the sentence
 * end_sec   = timestamp of the last word in the sentence
 * These per-sentence timestamps are non-overlapping and accurate, so the
 * backend can extract the correct source-audio slice for each sentence.
 */
function groupChunksToSentences(
  chunks: Array<{ text: string; timestamp: [number | null, number | null] }>,
): Array<{ text: string; start_sec: number; end_sec: number }> {
  const sentences: Array<{ text: string; start_sec: number; end_sec: number }> = []
  let buf = ''
  let start: number | null = null
  let end = 0

  for (const chunk of chunks) {
    const word = String(chunk.text || '').trim()
    if (!word) continue

    const chunkStart = chunk.timestamp[0] ?? 0
    const chunkEnd = chunk.timestamp[1] ?? end

    if (start === null) start = chunkStart
    end = chunkEnd
    buf += (buf ? ' ' : '') + word

    // Flush when buf ends with sentence-terminating punctuation,
    // but NOT when the last word is a known abbreviation (Mr., Dr., etc.)
    if (/[.!?]["'»]?\s*$/.test(buf)) {
      const lastWord = (buf.match(/([A-Za-z]+)[.!?]["'»]?\s*$/) ?? [])[1] ?? ''
      if (!ABBREVS.has(lastWord)) {
        sentences.push({ text: buf.trim(), start_sec: start, end_sec: end })
        buf = ''
        start = null
      }
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
    let lastMilestone = 0
    const streamer = new TextStreamer(t.tokenizer, {
      skip_prompt: true,
      skip_special_tokens: true,
    })
    const result: any = await t(audio, {
      // Word-level timestamps — each chunk is one word with its own precise
      // start/end time.  Matches reference word_timestamps=True behaviour:
      // non-overlapping per-sentence timestamps so backend extracts each
      // source-audio slice exactly once.
      return_timestamps: 'word',
      chunk_length_s: CHUNK_S,
      stride_length_s: STRIDE_S,
      streamer,
      chunk_callback: (_chunk: any) => {
        chunksProcessed++
        const pct = Math.min(99, Math.round((chunksProcessed / totalChunks) * 100))
        const milestone = Math.floor(pct / 25) * 25
        if (milestone > lastMilestone) {
          lastMilestone = milestone
          console.log('[Whisper] chunk', chunksProcessed, '/', totalChunks, `(${pct}%)`)
          self.postMessage({ type: 'progress', id, message: `Transcribing… ${milestone}%`, pct: milestone })
        }
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
