import type { VisualizerNode } from '../api/runtimeApi'

const DEFAULT_CANONICAL_PROVIDER = 'backend_m2m100'

function normalizeProviderKey(value: string | undefined): string {
  return String(value || '').trim().toLowerCase().replace(/-/g, '_').replace(/ /g, '_')
}

export function resolveNodeTranslation(
  node: VisualizerNode,
  preferredProvider?: string,
  canonicalProvider: string = DEFAULT_CANONICAL_PROVIDER,
): string {
  const translations = node.translations
  if (translations && typeof translations === 'object') {
    const preferredKey = normalizeProviderKey(preferredProvider || node.active_translation_provider)
    if (preferredKey) {
      const preferred = translations[preferredKey]
      const preferredText = String(preferred?.text || '').trim()
      if (preferredText) return preferredText
    }
    const canonical = translations[normalizeProviderKey(canonicalProvider)]
    const canonicalText = String(canonical?.text || '').trim()
    if (canonicalText) return canonicalText
    for (const row of Object.values(translations)) {
      const text = String(row?.text || '').trim()
      if (text) return text
    }
  }
  const legacy = String(node.translation?.text || '').trim()
  return legacy || '-'
}
