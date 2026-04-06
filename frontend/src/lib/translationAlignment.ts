import type { VisualizerNode } from '../api/runtimeApi'

const WORD_BOUNDARY_RE = /[\s.,!?;:()[\]{}"'`«»“”\-–—]/

type AlignmentResult = {
  alignedCount: number
  missingNodeTexts: string[]
}

function clamp(value: number, min: number, max: number): number {
  if (!Number.isFinite(value)) return min
  if (value < min) return min
  if (value > max) return max
  return value
}

function trimText(value: unknown): string {
  return String(value || '').trim()
}

function getProviderTranslation(node: VisualizerNode, provider: string): string {
  return trimText((node.translations as Record<string, { text?: string }> | undefined)?.[provider]?.text)
}

function isUsableTranslation(source: string, candidate: string): boolean {
  if (!candidate) return false
  return source.toLowerCase() !== candidate.toLowerCase()
}

function ensureNodeTranslation(
  node: VisualizerNode,
  provider: string,
  text: string,
  origin: 'sentence_alignment' | 'client_overlay',
): void {
  const normalized = trimText(text)
  if (!normalized) return
  node.translations = {
    ...(node.translations || {}),
    [provider]: {
      text: normalized,
      source_lang: 'en',
      target_lang: 'ru',
      origin,
    },
  }
  node.active_translation_provider = provider
}

function expandToWordStart(text: string, index: number): number {
  let i = clamp(index, 0, text.length)
  while (i > 0 && !WORD_BOUNDARY_RE.test(text[i - 1] || '')) i -= 1
  return i
}

function expandToWordEnd(text: string, index: number): number {
  let i = clamp(index, 0, text.length)
  while (i < text.length && !WORD_BOUNDARY_RE.test(text[i] || '')) i += 1
  return i
}

function extractAlignedSlice(params: {
  sourceSpan: { start: number; end: number } | undefined
  sourceSentenceLength: number
  translatedSentence: string
}): string {
  const { sourceSpan, sourceSentenceLength, translatedSentence } = params
  if (!sourceSpan) return ''
  const rawStart = Number(sourceSpan.start)
  const rawEnd = Number(sourceSpan.end)
  if (!Number.isFinite(rawStart) || !Number.isFinite(rawEnd)) return ''
  const sourceLen = Math.max(1, sourceSentenceLength)
  const targetLen = Math.max(1, translatedSentence.length)
  const start = clamp(Math.min(rawStart, rawEnd), 0, sourceLen)
  const end = clamp(Math.max(rawStart, rawEnd), start, sourceLen)
  if (end <= start) return ''

  const sourceShare = (end - start) / sourceLen
  const mappedStart = clamp(Math.floor((start / sourceLen) * targetLen), 0, targetLen)
  const mappedEnd = clamp(Math.ceil((end / sourceLen) * targetLen), mappedStart, targetLen)
  if (mappedEnd <= mappedStart) return ''

  const expandedStart = expandToWordStart(translatedSentence, mappedStart)
  const expandedEnd = expandToWordEnd(translatedSentence, mappedEnd)
  const expanded = trimText(translatedSentence.slice(expandedStart, expandedEnd))
  const strict = trimText(translatedSentence.slice(mappedStart, mappedEnd))
  const candidate = expanded || strict
  if (!candidate) return ''

  // Guard against pathological slices where a tiny source node captures almost
  // the full translated sentence after boundary expansion.
  const targetShare = candidate.length / targetLen
  if (sourceShare <= 0.08 && targetShare >= 0.35) return ''
  if (sourceShare <= 0.2 && targetShare >= 0.8) return ''
  return candidate
}

export function alignNodeTranslationsFromSentence(params: {
  root: VisualizerNode
  sentenceSourceText: string
  sentenceTranslatedText: string
  provider: string
}): AlignmentResult {
  const sourceSentence = trimText(params.sentenceSourceText)
  const translatedSentence = trimText(params.sentenceTranslatedText)
  const provider = trimText(params.provider)
  if (!translatedSentence || !provider) {
    return { alignedCount: 0, missingNodeTexts: [] }
  }

  const missing = new Set<string>()
  let alignedCount = 0
  const stack: VisualizerNode[] = [params.root]

  while (stack.length > 0) {
    const node = stack.pop() as VisualizerNode
    const content = trimText(node.content)
    const existing = getProviderTranslation(node, provider)
    if (content) {
      if (isUsableTranslation(content, existing)) {
        node.active_translation_provider = provider
      } else {
        const alignedText = node === params.root
          ? translatedSentence
          : extractAlignedSlice({
              sourceSpan: node.source_span,
              sourceSentenceLength: sourceSentence.length || content.length,
              translatedSentence,
            })
        if (isUsableTranslation(content, alignedText)) {
          ensureNodeTranslation(node, provider, alignedText, 'sentence_alignment')
          alignedCount += 1
        } else if (node.part_of_speech !== 'punctuation') {
          missing.add(content)
        }
      }
    }
    for (const child of node.linguistic_elements || []) stack.push(child)
  }

  return {
    alignedCount,
    missingNodeTexts: Array.from(missing),
  }
}

export function fillMissingNodeTranslations(params: {
  root: VisualizerNode
  provider: string
  translationMap: Record<string, string>
}): number {
  const provider = trimText(params.provider)
  if (!provider || !params.translationMap || Object.keys(params.translationMap).length === 0) return 0
  let filledCount = 0
  const stack: VisualizerNode[] = [params.root]

  while (stack.length > 0) {
    const node = stack.pop() as VisualizerNode
    const content = trimText(node.content)
    const existing = getProviderTranslation(node, provider)
    if (content && !isUsableTranslation(content, existing)) {
      const translated = trimText(params.translationMap[content])
      if (isUsableTranslation(content, translated)) {
        ensureNodeTranslation(node, provider, translated, 'client_overlay')
        filledCount += 1
      }
    } else if (content && isUsableTranslation(content, existing)) {
      node.active_translation_provider = provider
    }
    for (const child of node.linguistic_elements || []) stack.push(child)
  }

  return filledCount
}
