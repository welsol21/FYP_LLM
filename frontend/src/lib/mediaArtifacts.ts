import type { DocumentArtifact } from '../api/runtimeApi'

export type ArtifactSentenceRow = {
  sentence_idx: number
  sentence_text: string
  sentence_hash: string
  text_eng: string
  text_ru: string
  start: number
  end: number
  start_ms: number
  end_ms: number
  units: unknown[]
  units_ru: unknown[]
}

export type TimedSentenceRow = {
  text: string
  start_ms: number
  end_ms: number
}

export function inferSourceKind(mediaPath: string, mimeType?: string): 'text' | 'audio' | 'video' | 'other' {
  const ext = String(mediaPath || '').toLowerCase()
  const mime = String(mimeType || '').toLowerCase()
  if (mime.startsWith('text/')) return 'text'
  if (mime.startsWith('audio/')) return 'audio'
  if (mime.startsWith('video/')) return 'video'
  if (ext.endsWith('.txt') || ext.endsWith('.md') || ext.endsWith('.srt') || ext.endsWith('.vtt') || ext.endsWith('.json')) return 'text'
  if (ext.endsWith('.mp3') || ext.endsWith('.wav') || ext.endsWith('.m4a') || ext.endsWith('.flac') || ext.endsWith('.ogg')) return 'audio'
  if (ext.endsWith('.mp4') || ext.endsWith('.mkv') || ext.endsWith('.mov') || ext.endsWith('.avi') || ext.endsWith('.webm')) return 'video'
  return 'other'
}

export function normalizeText(raw: string): string {
  return String(raw || '')
    .replace(/\r\n/g, '\n')
    .replace(/[ \t]+/g, ' ')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

export function stripSubtitleMarkup(raw: string): string {
  const lines = raw
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line.length > 0)
    .filter((line) => !/^\d+$/.test(line))
    .filter((line) => !/^\d{2}:\d{2}:\d{2}[,.]\d{3}\s+-->\s+\d{2}:\d{2}:\d{2}[,.]\d{3}/.test(line))
    .filter((line) => line.toUpperCase() !== 'WEBVTT')
  return lines.join(' ')
}

export function splitIntoSentences(rawText: string): string[] {
  return normalizeText(rawText)
    .split(/(?<=[.!?])\s+/)
    .map((s) => s.trim())
    .filter(Boolean)
}

export function normalizeContractError(): string {
  return 'Project service is unavailable. Check internet access and service URL.'
}

export function bytesOfText(text: string): number {
  return new TextEncoder().encode(text).length
}

export function encodeTextArtifact(mime: string, text: string): string {
  return `data:${mime};charset=utf-8,${encodeURIComponent(text)}`
}

export function simpleHash(input: string): string {
  let h = 2166136261
  for (let i = 0; i < input.length; i += 1) {
    h ^= input.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return `h${(h >>> 0).toString(16)}`
}

export function formatSrtTime(ms: number): string {
  const safe = Math.max(0, Math.floor(ms))
  const hours = Math.floor(safe / 3600000)
  const minutes = Math.floor((safe % 3600000) / 60000)
  const seconds = Math.floor((safe % 60000) / 1000)
  const millis = safe % 1000
  const pad = (value: number, len: number): string => String(value).padStart(len, '0')
  return `${pad(hours, 2)}:${pad(minutes, 2)}:${pad(seconds, 2)},${pad(millis, 3)}`
}

export function buildSrt(rows: ArtifactSentenceRow[], bilingual: boolean): string {
  const blocks = rows
    .map((row, idx) => {
      const lines = bilingual
        ? [String(row.text_eng || '').trim(), String(row.text_ru || '').trim()].filter(Boolean)
        : [String(row.text_eng || '').trim()].filter(Boolean)
      if (lines.length === 0) return ''
      return [
        String(idx + 1),
        `${formatSrtTime(row.start_ms)} --> ${formatSrtTime(Math.max(row.end_ms, row.start_ms + 800))}`,
        ...lines,
        '',
      ].join('\n')
    })
    .filter(Boolean)
  return blocks.join('\n')
}

export function buildMediaSentenceRows(
  sentences: string[],
  translatedSentences: string[],
  timedSentences?: TimedSentenceRow[],
): ArtifactSentenceRow[] {
  return sentences.map((sentence, idx) => {
    const timed = timedSentences?.[idx]
    const startMs = typeof timed?.start_ms === 'number' ? Math.max(0, timed.start_ms) : idx * 3000
    const endMs = typeof timed?.end_ms === 'number' ? Math.max(startMs + 300, timed.end_ms) : startMs + 2600
    return {
      sentence_idx: idx,
      sentence_text: sentence,
      sentence_hash: simpleHash(`${idx}:${sentence}`),
      text_eng: sentence,
      text_ru: String(translatedSentences[idx] || '').trim(),
      start: startMs / 1000,
      end: endMs / 1000,
      start_ms: startMs,
      end_ms: endMs,
      units: [],
      units_ru: [],
    }
  })
}

export function extractMediaSentencesFromArtifacts(artifacts: DocumentArtifact[]): ArtifactSentenceRow[] {
  const mediaContract = artifacts.find((row) => row.name === 'media_contract.json')
  if (!mediaContract?.download_url?.startsWith('data:')) return []
  try {
    const payload = decodeURIComponent(String(mediaContract.download_url).split(',', 2)[1] || '')
    const parsed = JSON.parse(payload) as { media_sentences?: unknown[] }
    if (!Array.isArray(parsed.media_sentences)) return []
    return parsed.media_sentences.map((row, idx) => {
      const item = (row || {}) as Record<string, unknown>
      return {
        sentence_idx: Number(item.sentence_idx ?? idx),
        sentence_text: String(item.sentence_text || item.text_eng || ''),
        sentence_hash: String(item.sentence_hash || simpleHash(`${idx}:${String(item.sentence_text || item.text_eng || '')}`)),
        text_eng: String(item.text_eng || item.sentence_text || ''),
        text_ru: String(item.text_ru || ''),
        start: Number(item.start || 0),
        end: Number(item.end || 0),
        start_ms: Number(item.start_ms || 0),
        end_ms: Number(item.end_ms || 0),
        units: Array.isArray(item.units) ? item.units : [],
        units_ru: Array.isArray(item.units_ru) ? item.units_ru : [],
      }
    })
  } catch {
    return []
  }
}

export async function extractRawTextFromBlob(blob: Blob, mediaPath: string): Promise<string> {
  const kind = inferSourceKind(mediaPath, blob.type)
  if (kind !== 'text') return ''
  const text = typeof (blob as Blob & { text?: () => Promise<string> }).text === 'function'
    ? await (blob as Blob & { text: () => Promise<string> }).text()
    : await new Response(blob).text()
  if (mediaPath.toLowerCase().endsWith('.srt') || mediaPath.toLowerCase().endsWith('.vtt')) {
    return normalizeText(stripSubtitleMarkup(text))
  }
  return normalizeText(text)
}

export function replaceTextArtifact(artifacts: DocumentArtifact[], name: string, mime: string, text: string): void {
  const content = String(text || '').trim()
  if (!content) return
  const next: DocumentArtifact = {
    name,
    size_bytes: bytesOfText(content),
    download_url: encodeTextArtifact(mime, content),
  }
  const idx = artifacts.findIndex((row) => String(row?.name || '') === name)
  if (idx >= 0) artifacts[idx] = next
  else artifacts.push(next)
}
