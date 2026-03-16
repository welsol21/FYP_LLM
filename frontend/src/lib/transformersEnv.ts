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

// Pre-fetches the ONNX JSEP module and sets wasmPaths.mjs to a blob URL.
//
// WebKitGTK on Linux cannot dynamic import() ES modules from tauri:// URLs.
// ONNX Runtime Web normally bypasses this by fetching cross-origin URLs into
// blob URLs before importing — but it only does this when numThreads > 1,
// which requires SharedArrayBuffer (COOP/COEP headers that Tauri doesn't set).
// With numThreads=1 (the Tauri default), ONNX always tries import(tauri://...)
// which fails. Fix: pre-fetch the .mjs ourselves and supply a blob: URL via
// env.backends.onnx.wasm.wasmPaths.mjs so ONNX imports from blob: instead.
async function patchOnnxJsepBlobUrl(record: TransformersEnv): Promise<void> {
  const backends = record.backends as Record<string, unknown> | undefined
  const onnx = backends?.onnx as Record<string, unknown> | undefined
  const wasm = onnx?.wasm as Record<string, unknown> | undefined
  if (!wasm || typeof wasm !== 'object') return

  // The .mjs file is served at the same path relative to the bundle.
  const mjsUrl = new URL('/assets/ort-wasm-simd-threaded.jsep.mjs', location.href).href
  let text = await fetch(mjsUrl).then((r) => {
    if (!r.ok) throw new Error(`fetch ${mjsUrl}: ${r.status}`)
    return r.text()
  })
  // Patch relative .wasm references inside the module so they resolve correctly
  // when imported from a blob: URL (blob URLs have no directory base).
  const wasmUrl = new URL('/assets/ort-wasm-simd-threaded.jsep.wasm', location.href).href
  text = text.replace(/"ort-wasm-simd-threaded\.jsep\.wasm"/g, JSON.stringify(wasmUrl))
  text = text.replace(/'ort-wasm-simd-threaded\.jsep\.wasm'/g, JSON.stringify(wasmUrl))
  const blobUrl = URL.createObjectURL(new Blob([text], { type: 'text/javascript' }))

  // env.backends.onnx.wasm properties may be defined as non-writable via
  // Object.defineProperty in ONNX Runtime. Use defineProperty to override.
  const existing = wasm.wasmPaths
  const merged = (existing && typeof existing === 'object')
    ? { ...(existing as Record<string, unknown>), mjs: blobUrl }
    : { mjs: blobUrl }
  Object.defineProperty(wasm, 'wasmPaths', {
    value: merged,
    writable: true,
    configurable: true,
    enumerable: true,
  })
}

export async function configureTransformersEnv(env: unknown): Promise<void> {
  return configureTransformersEnvForMode(env)
}

export async function configureTransformersEnvForMode(env: unknown, mode: 'desktop' | 'pwa' = 'pwa'): Promise<void> {
  if (!env || typeof env !== 'object') return
  const record = env as TransformersEnv
  record.allowLocalModels = mode === 'desktop'
  record.allowRemoteModels = mode !== 'desktop'
  record.useBrowserCache = browserCacheAvailable()

  if (mode === 'desktop') {
    await patchOnnxJsepBlobUrl(record)
  }
}
