import type { VisualizerNode } from '../api/runtimeApi'

const DEFAULT_CANONICAL_PROVIDER = 'backend_m2m100'

function normalizeProviderKey(value: string | undefined): string {
  return String(value || '').trim().toLowerCase().replace(/-/g, '_').replace(/ /g, '_')
}

function canonicalizeProviderKey(value: string | undefined): string {
  const normalized = normalizeProviderKey(value)
  if (!normalized) return ''
  if (normalized.startsWith('backend_')) return normalized.slice('backend_'.length)
  return normalized
}

function buildTranslationIndex(
  translations: Record<string, { text?: string }>,
): Map<string, string> {
  const index = new Map<string, string>()
  for (const [provider, row] of Object.entries(translations)) {
    const key = normalizeProviderKey(provider)
    if (!key || index.has(key)) continue
    const text = String(row?.text || '').trim()
    if (!text) continue
    index.set(key, text)
  }
  return index
}

function resolveByCanonicalProvider(
  index: Map<string, string>,
  provider: string | undefined,
): TranslationVariant | null {
  const canonical = canonicalizeProviderKey(provider)
  if (!canonical) return null
  const candidates = new Set<string>([canonical, `backend_${canonical}`])
  for (const candidate of candidates) {
    const text = index.get(candidate)
    if (!text) continue
    return { provider: canonical, text }
  }
  return null
}

export function resolveNodeTranslation(
  node: VisualizerNode,
  preferredProvider?: string,
  canonicalProvider: string = DEFAULT_CANONICAL_PROVIDER,
): string {
  return resolveNodeTranslationVariant(node, preferredProvider, canonicalProvider).text
}

export type TranslationVariant = {
  provider: string
  text: string
}

export function resolveNodeTranslationVariant(
  node: VisualizerNode,
  preferredProvider?: string,
  canonicalProvider: string = DEFAULT_CANONICAL_PROVIDER,
): TranslationVariant {
  const translations = node.translations
  if (!translations || typeof translations !== 'object') {
    return { provider: '', text: '-' }
  }

  const index = buildTranslationIndex(translations)
  const preferredResolved = resolveByCanonicalProvider(index, preferredProvider || node.active_translation_provider)
  if (preferredResolved) return preferredResolved

  const canonicalResolved = resolveByCanonicalProvider(index, canonicalProvider)
  if (canonicalResolved) return canonicalResolved

  for (const [provider, text] of index.entries()) {
    if (!text) continue
    return { provider: canonicalizeProviderKey(provider), text }
  }

  return { provider: '', text: '-' }
}

export function listAlternativeTranslations(
  node: VisualizerNode,
  preferredProvider?: string,
  canonicalProvider: string = DEFAULT_CANONICAL_PROVIDER,
): TranslationVariant[] {
  const translations = node.translations
  if (!translations || typeof translations !== 'object') return []
  const selectedProviderCanonical = resolveNodeTranslationVariant(node, preferredProvider, canonicalProvider).provider
  const out: TranslationVariant[] = []
  const seenProviders = new Set<string>()
  for (const [provider, row] of Object.entries(translations)) {
    const key = canonicalizeProviderKey(provider)
    const text = String(row?.text || '').trim()
    if (!text) continue
    if (key === selectedProviderCanonical) continue
    if (seenProviders.has(key)) continue
    out.push({ provider: key || provider, text })
    seenProviders.add(key)
  }
  return out
}
