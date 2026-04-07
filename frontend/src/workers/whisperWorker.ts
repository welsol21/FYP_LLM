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

// Bibliographic credit markers — mirror of server-side _BIBLIOGRAPHIC_MARKERS.
const BIBLIOGRAPHIC_MARKERS = [
  'written by', 'translated by', 'translated from', 'read by',
  'narrated by', 'performed by', 'adapted by', 'illustrated by',
  'edited by', 'published by', 'produced by',
]

// Common English finite-verb forms.  If any of these appear as a standalone
// word the text is likely a real sentence, not a heading.
const FINITE_VERB_RE = /\b(is|are|was|were|has|have|had|do|does|did|will|would|could|should|can|may|might|must|shall|'s|'re|'ve|'ll|'d)\b/i

// Ordinal/cardinal words that commonly end chapter titles.
const ORDINAL_WORD_RE = /^(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|I{1,3}|IV|VI{0,3}|VIII|IX|X)$/i

/**
 * Returns true when `buf` looks like a chapter-heading fragment that ended
 * with a numeral or ordinal word, e.g. "The Voice of Reason 3" or
 * "Part One".  Used to force-flush even without terminal punctuation.
 */
function looksLikeHeadingEnd(buf: string): boolean {
  const words = buf.trim().split(/\s+/)
  if (words.length < 2 || words.length > 8) return false
  const last = words[words.length - 1]
  if (!/^\d+$/.test(last) && !ORDINAL_WORD_RE.test(last)) return false
  // All alpha words must be title-cased (heading convention).
  const alphaWords = words.filter((w) => /^[a-zA-Z]/.test(w))
  if (!alphaWords.every((w) => /^[A-Z]/.test(w))) return false
  if (FINITE_VERB_RE.test(buf)) return false
  return true
}

/**
 * Returns true when `text` is a chapter heading or bibliographic credit line
 * that should be excluded from the subtitle track.
 * Mirrors the server-side _is_metadata_like_sentence heuristic.
 */
function isMetadataLike(text: string): boolean {
  const lower = text.trim().toLowerCase()
  if (!lower) return true
  if (BIBLIOGRAPHIC_MARKERS.some((m) => lower.includes(m))) return true
  // Heading-like: ≤6 alpha words, title case, no finite verb.
  const alphaWords = text.match(/\b[a-zA-Z]+\b/g) ?? []
  if (
    alphaWords.length <= 6 &&
    alphaWords.every((w) => /^[A-Z]/.test(w)) &&
    !FINITE_VERB_RE.test(text)
  ) return true
  return false
}

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
 *
 * Additionally:
 * - "The Voice of Reason 3" (no period) is flushed via looksLikeHeadingEnd.
 * - Chapter headings and bibliographic credits are filtered out afterwards.
 * - If the filter would remove every sentence, it falls back to the unfiltered list.
 */
function groupChunksToSentences(
  chunks: Array<{ text: string; timestamp: [number | null, number | null] }>,
): Array<{ text: string; start_sec: number; end_sec: number }> {
  const sentences: Array<{ text: string; start_sec: number; end_sec: number }> = []
  let buf = ''
  let start: number | null = null
  let end = 0

  const flushBuf = (): void => {
    const text = buf.trim()
    if (text && start !== null) {
      sentences.push({ text, start_sec: start, end_sec: end })
    }
    buf = ''
    start = null
  }

  for (const chunk of chunks) {
    const word = String(chunk.text || '').trim()
    if (!word) continue

    const chunkStart = chunk.timestamp[0] ?? 0
    const chunkEnd = chunk.timestamp[1] ?? end

    if (start === null) start = chunkStart
    end = chunkEnd
    buf += (buf ? ' ' : '') + word

    // Flush on sentence-terminal punctuation (skip known abbreviations).
    if (/[.!?]["'»]?\s*$/.test(buf)) {
      const lastWord = (buf.match(/([A-Za-z]+)[.!?]["'»]?\s*$/) ?? [])[1] ?? ''
      if (!ABBREVS.has(lastWord)) {
        flushBuf()
        continue
      }
    }

    // Force-flush when the buffer looks like a heading ending with a numeral
    // or ordinal, e.g. "The Voice of Reason 3" (Whisper omits the period).
    if (looksLikeHeadingEnd(buf)) {
      flushBuf()
    }
  }

  flushBuf()

  // Remove chapter headings and bibliographic credits from the subtitle list.
  const filtered = sentences.filter((s) => !isMetadataLike(s.text))
  // Fallback: if the filter removed everything, keep the original list.
  return filtered.length > 0 ? filtered : sentences
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
