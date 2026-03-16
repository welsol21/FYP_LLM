// Client that manages the ML pipeline Web Worker instance and exposes an
// async API matching the existing pipeline functions in clientAsr.ts,
// desktopMediaFlow.ts and clientMediaRender.ts.

import type { DetailedAsrResult, TimedSentence } from './clientAsr'

export type MlProgressCallback = (message: string, progress: number) => void

type TtsWorkerResult = { audio: Float32Array; sampling_rate: number }

type PendingEntry = {
  resolve: (value: unknown) => void
  reject: (error: Error) => void
  onProgress?: MlProgressCallback
}

type WorkerResponse =
  | { id: string; type: 'PROGRESS'; message: string; progress: number }
  | { id: string; type: 'RESULT'; payload: unknown }
  | { id: string; type: 'ERROR'; message: string }

function generateId(): string {
  return typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`
}

class MlWorkerClient {
  private worker: Worker | null = null
  private pending = new Map<string, PendingEntry>()

  private getWorker(): Worker {
    if (!this.worker) {
      // Use the URL constructor so Vite detects and bundles the worker.
      // type:'classic' is required because WebKitGTK does not support module workers.
      this.worker = new Worker(
        new URL('../workers/mlPipeline.worker.ts', import.meta.url),
        { type: 'classic' },
      )
      this.worker.onmessage = (event: MessageEvent<WorkerResponse>) => {
        this.handleMessage(event.data)
      }
      this.worker.onerror = (event: ErrorEvent) => {
        const message = event?.message || 'ML worker encountered an unhandled error.'
        // Reject all pending requests
        for (const [id, entry] of this.pending) {
          entry.reject(new Error(message))
          this.pending.delete(id)
        }
      }
    }
    return this.worker
  }

  private handleMessage(data: WorkerResponse): void {
    if (!data || typeof data !== 'object' || !data.id) return
    const entry = this.pending.get(data.id)
    if (!entry) return

    switch (data.type) {
      case 'PROGRESS':
        entry.onProgress?.(data.message, data.progress)
        break
      case 'RESULT':
        this.pending.delete(data.id)
        entry.resolve(data.payload)
        break
      case 'ERROR':
        this.pending.delete(data.id)
        entry.reject(new Error(data.message))
        break
      default:
        break
    }
  }

  private send<T>(
    message: Record<string, unknown>,
    transfers: Transferable[],
    onProgress?: MlProgressCallback,
  ): Promise<T> {
    const id = generateId()
    const worker = this.getWorker()
    return new Promise<T>((resolve, reject) => {
      this.pending.set(id, {
        resolve: resolve as (value: unknown) => void,
        reject,
        onProgress,
      })
      worker.postMessage({ ...message, id }, transfers)
    })
  }

  // -------------------------------------------------------------------------
  // Public API
  // -------------------------------------------------------------------------

  async runAsr(
    audioData: Float32Array,
    sampleRate: number,
    modelPath: string,
    onProgress?: MlProgressCallback,
  ): Promise<DetailedAsrResult> {
    const result = await this.send<unknown>(
      { type: 'ASR', audioData, sampleRate, modelPath },
      [audioData.buffer],
      onProgress,
    )
    return parseAsrResult(result)
  }

  async runTranslate(
    sentences: string[],
    modelPath: string,
    onProgress?: MlProgressCallback,
  ): Promise<string[]> {
    const result = await this.send<unknown>(
      { type: 'TRANSLATE', sentences, modelPath },
      [],
      onProgress,
    )
    if (Array.isArray(result)) return result as string[]
    return []
  }

  async runTts(
    sentences: string[],
    modelPath: string,
    onProgress?: MlProgressCallback,
  ): Promise<TtsWorkerResult[]> {
    const result = await this.send<unknown>(
      { type: 'TTS', sentences, modelPath },
      [],
      onProgress,
    )
    if (Array.isArray(result)) return result as TtsWorkerResult[]
    return []
  }
}

// ---------------------------------------------------------------------------
// Parse ASR result — mirrors buildTimedSentencesFromResult in clientAsr.ts
// ---------------------------------------------------------------------------

function chunkText(value: unknown): string {
  return String(value || '').replace(/\s+/g, ' ').trim()
}

function isSentenceEnd(text: string): boolean {
  return /[.!?]["')\]]*$/.test(String(text || '').trim())
}

function buildTimedSentencesFromWorkerResult(result: unknown): TimedSentence[] {
  const chunks = Array.isArray((result as { chunks?: unknown[] } | null | undefined)?.chunks)
    ? ((result as { chunks: unknown[] }).chunks as unknown[])
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

function parseAsrResult(result: unknown): DetailedAsrResult {
  if (typeof result === 'string') return { text: result.trim(), sentences: [] }
  if (result && typeof result === 'object' && 'text' in result) {
    return {
      text: String((result as { text?: string }).text || '').trim(),
      sentences: buildTimedSentencesFromWorkerResult(result),
    }
  }
  return { text: '', sentences: [] }
}

// ---------------------------------------------------------------------------
// Singleton
// ---------------------------------------------------------------------------

export const mlWorkerClient = new MlWorkerClient()
export type { TtsWorkerResult }
