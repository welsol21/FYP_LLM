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
  if (!env || typeof env !== 'object') return
  const record = env as TransformersEnv
  record.allowLocalModels = false
  record.allowRemoteModels = true
  record.useBrowserCache = browserCacheAvailable()
}
