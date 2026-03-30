import type { VisualizerNode } from '../api/runtimeApi'

const DEFAULT_CANONICAL_PROVIDER = 'm2m100'

function normalizeProviderKey(value: string | undefined): string {
  return String(value || '').trim().toLowerCase().replace(/-/g, '_').replace(/ /g, '_')
}

function canonicalizeProviderKey(value: string | undefined): string {
  const normalized = normalizeProviderKey(value)
  return normalized || ''
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
  const text = index.get(canonical)
  return text ? { provider: canonical, text } : null
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

  // If a provider was explicitly chosen by the user, do not fall back to another provider.
  if (preferredProvider && normalizeProviderKey(preferredProvider)) {
    const canonical = canonicalizeProviderKey(preferredProvider)
    const text = index.get(canonical)
    return text ? { provider: canonical, text } : { provider: canonical, text: '-' }
  }

  // No explicit preferred — use active_translation_provider, then canonical, then any.
  const activeResolved = resolveByCanonicalProvider(index, node.active_translation_provider)
  if (activeResolved) return activeResolved

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
