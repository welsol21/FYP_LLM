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
  // Models are served locally — no CDN downloads allowed.
  record.allowLocalModels = true
  record.allowRemoteModels = false
  record.localModelPath = '/models/'
  record.useBrowserCache = browserCacheAvailable()
  // ONNX Runtime WASM files served locally — enables multi-threaded CPU inference.
  const onnxEnv = (record.backends as any)?.onnx
  if (onnxEnv?.wasm) onnxEnv.wasm.wasmPaths = '/onnx/'
}
