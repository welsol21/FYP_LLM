type TransformersEnv = Record<string, unknown>

export function browserCacheAvailable(): boolean {
  try {
    return typeof globalThis !== 'undefined'
      && typeof (globalThis as typeof globalThis & { caches?: CacheStorage }).caches?.open === 'function'
      && (typeof globalThis.isSecureContext !== 'boolean' || globalThis.isSecureContext)
  } catch {
    return false
  }
}

export function configureTransformersEnv(env: unknown): void {
  configureTransformersEnvForMode(env)
}

export function configureTransformersEnvForMode(env: unknown, mode: 'desktop' | 'pwa' = 'pwa'): void {
  if (!env || typeof env !== 'object') return
  const record = env as TransformersEnv
  record.allowLocalModels = mode === 'desktop'
  record.allowRemoteModels = mode !== 'desktop'
  record.useBrowserCache = browserCacheAvailable()
}
