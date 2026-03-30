export type ParsedAnalysisSettings = {
  translator?: string
  subtitles?: string
  voice?: string
  processing?: string
}

export type AnalysisFeatureBadge = {
  key: 'translator' | 'subtitles' | 'voice' | 'processing'
  label: string
  value: string
}

function normalizeRawValue(value: string): string {
  return String(value || '')
    .trim()
    .toLowerCase()
    .replace(/\s+/g, '_')
}

function prettifyTranslator(value: string): string {
  if (value === 'm2m100') return 'M2M100'
  if (value === 'huggingface') return 'HuggingFace'
  if (value === 'none') return 'None'
  return value
}

function prettifySubtitles(value: string): string {
  if (value === 'bilingual_sequential') return 'Bi-seq'
  if (value === 'bilingual_simultaneous') return 'Bi-sim'
  if (value === 'target_only') return 'Target'
  if (value === 'source_only') return 'Source'
  if (value === 'bilingual') return 'Bilingual'
  return value
}

function prettifyVoice(value: string): string {
  if (!value) return value
  return value.charAt(0).toUpperCase() + value.slice(1)
}

function prettifyProcessing(value: string): string {
  if (value === 'incremental') return 'Reuse'
  if (value === 'force') return 'Force'
  return value
}

export function parseAnalysisSettings(settings: string): ParsedAnalysisSettings {
  const parsed: ParsedAnalysisSettings = {}
  const parts = String(settings || '')
    .split('/')
    .map((part) => part.trim())
    .filter(Boolean)

  for (const part of parts) {
    const match = part.match(/^([^:]+):\s*(.+)$/)
    if (!match) continue
    const key = normalizeRawValue(match[1])
    const value = normalizeRawValue(match[2])
    if (!value) continue
    if (key === 'transl' || key === 'translator') parsed.translator = value
    else if (key === 'subs' || key === 'subtitles') parsed.subtitles = value
    else if (key === 'voice') parsed.voice = value
    else if (key === 'proc' || key === 'processing') parsed.processing = value
  }
  return parsed
}

export function getTranslationProviderFromSettings(settings: string, fallback = 'm2m100'): string {
  const parsed = parseAnalysisSettings(settings)
  return parsed.translator || fallback
}

// Maps internal artifact names to clean file suffixes (extension with optional type tag)
const ARTIFACT_SUFFIX: Record<string, string> = {
  'translated_video_ru.mp4': '.mp4',
  'translated_audio_ru.mp3': '.mp3',
  'subtitles_en.srt': '_en.srt',
  'subtitles_bilingual.srt': '_bilingual.srt',
  'subtitles_target.srt': '_target.srt',
  'media_contract.json': '_contract.json',
}

function shortVoice(raw: string): string {
  const v = (raw || '').toLowerCase().replace(/[^a-z]/g, '')
  if (v.includes('svetlana')) return 'svetlana'
  if (v.includes('dmitry') || v.includes('dmitri')) return 'dmitry'
  return v || ''
}

function shortSubs(raw: string): string {
  const v = (raw || '').toLowerCase().replace(/[^a-z_]/g, '')
  if (v === 'bilingual_sequential') return 'bilingual'
  if (v === 'bilingual_simultaneous') return 'bilingual_sim'
  if (v.includes('target')) return 'target'
  if (v.includes('source')) return 'source'
  return v || ''
}

/** Build the user-facing download filename: {file_stem}_{voice}_{subs}{clean_suffix} */
export function buildExportFileName(fileName: string, settings: string, artifactName: string): string {
  const stem = String(fileName || '').replace(/\.[^.]+$/, '').trim()
  const parsed = parseAnalysisSettings(settings)
  const voice = shortVoice(parsed.voice || '')
  const subs = shortSubs(parsed.subtitles || '')
  const features = [voice, subs].filter(Boolean)
  const suffix = ARTIFACT_SUFFIX[artifactName] ?? `_${artifactName}`
  return [stem, ...features].filter(Boolean).join('_') + suffix
}

export function buildAnalysisFeatureBadges(settings: string): AnalysisFeatureBadge[] {
  const parsed = parseAnalysisSettings(settings)
  const out: AnalysisFeatureBadge[] = []
  if (parsed.translator) out.push({ key: 'translator', label: 'Transl', value: prettifyTranslator(parsed.translator) })
  if (parsed.subtitles) out.push({ key: 'subtitles', label: 'Subs', value: prettifySubtitles(parsed.subtitles) })
  if (parsed.voice) out.push({ key: 'voice', label: 'Voice', value: prettifyVoice(parsed.voice) })
  if (parsed.processing) out.push({ key: 'processing', label: 'Proc', value: prettifyProcessing(parsed.processing) })
  return out
}
