const APP_SHELL_CACHE = 'ela-app-shell-v6'
const RUNTIME_CACHE = 'ela-runtime-v6'
const MODELS_CACHE = 'ela-models-v1'

const APP_SHELL_FILES = [
  '/manifest.webmanifest',
  '/offline.html',
  '/icon-192.png',
  '/icon-512.png',
  '/icon-maskable-192.png',
  '/icon-maskable-512.png',
  '/apple-touch-icon.png',
]

// Model files served from the same origin under /models/.
// Downloaded once into MODELS_CACHE, then served cache-first (offline capable).
const MODEL_FILES = [
  // Whisper base.en (WASM q8)
  '/models/Xenova/whisper-base.en/config.json',
  '/models/Xenova/whisper-base.en/generation_config.json',
  '/models/Xenova/whisper-base.en/preprocessor_config.json',
  '/models/Xenova/whisper-base.en/quant_config.json',
  '/models/Xenova/whisper-base.en/added_tokens.json',
  '/models/Xenova/whisper-base.en/merges.txt',
  '/models/Xenova/whisper-base.en/normalizer.json',
  '/models/Xenova/whisper-base.en/tokenizer.json',
  '/models/Xenova/whisper-base.en/tokenizer_config.json',
  '/models/Xenova/whisper-base.en/vocab.json',
  '/models/Xenova/whisper-base.en/onnx/encoder_model_quantized.onnx',
  '/models/Xenova/whisper-base.en/onnx/decoder_model_merged_quantized.onnx',
  // Translation opus-mt-en-ru (WASM q8)
  '/models/Xenova/opus-mt-en-ru/config.json',
  '/models/Xenova/opus-mt-en-ru/generation_config.json',
  '/models/Xenova/opus-mt-en-ru/quantize_config.json',
  '/models/Xenova/opus-mt-en-ru/source.spm',
  '/models/Xenova/opus-mt-en-ru/target.spm',
  '/models/Xenova/opus-mt-en-ru/special_tokens_map.json',
  '/models/Xenova/opus-mt-en-ru/tokenizer.json',
  '/models/Xenova/opus-mt-en-ru/tokenizer_config.json',
  '/models/Xenova/opus-mt-en-ru/vocab.json',
  '/models/Xenova/opus-mt-en-ru/onnx/encoder_model_quantized.onnx',
  '/models/Xenova/opus-mt-en-ru/onnx/decoder_model_merged_quantized.onnx',
  // TTS mms-tts-rus (quantized)
  '/models/Xenova/mms-tts-rus/config.json',
  '/models/Xenova/mms-tts-rus/added_tokens.json',
  '/models/Xenova/mms-tts-rus/special_tokens_map.json',
  '/models/Xenova/mms-tts-rus/tokenizer.json',
  '/models/Xenova/mms-tts-rus/tokenizer_config.json',
  '/models/Xenova/mms-tts-rus/vocab.json',
  '/models/Xenova/mms-tts-rus/quantize_config.json',
  '/models/Xenova/mms-tts-rus/onnx/model_quantized.onnx',
]

self.addEventListener('install', (event) => {
  event.waitUntil(
    Promise.all([
      caches.open(APP_SHELL_CACHE).then((cache) => cache.addAll(APP_SHELL_FILES)),
      // Pre-cache model files in background — failures are non-fatal (models may
      // not be on server yet; user will get "install PWA" error at runtime instead).
      caches.open(MODELS_CACHE).then((cache) =>
        Promise.allSettled(MODEL_FILES.map((url) => cache.add(url))),
      ),
    ]),
  )
  self.skipWaiting()
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key !== APP_SHELL_CACHE && key !== RUNTIME_CACHE && key !== MODELS_CACHE)
          .map((key) => caches.delete(key)),
      ),
    ).then(() => self.clients.claim()),
  )
})

self.addEventListener('fetch', (event) => {
  const request = event.request
  if (request.method !== 'GET') return

  const url = new URL(request.url)
  const isSameOrigin = url.origin === self.location.origin

  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request, { cache: 'no-store' })
        .then((response) => response)
        .catch(async () => {
          return (await caches.match('/offline.html')) || Response.error()
        }),
    )
    return
  }

  if (!isSameOrigin) return

  // Model files: cache-first (large binaries, never change for a given version)
  if (url.pathname.startsWith('/models/')) {
    event.respondWith(
      caches.open(MODELS_CACHE).then(async (cache) => {
        const cached = await cache.match(request)
        if (cached) return cached
        const response = await fetch(request)
        if (response.ok) cache.put(request, response.clone()).catch(() => undefined)
        return response
      }),
    )
    return
  }

  const cacheableAsset = /\.(js|mjs|css|png|svg|ico|webmanifest|wasm|ttf)$/i.test(url.pathname)
  if (!cacheableAsset) return

  event.respondWith(
    fetch(request)
      .then((response) => {
        if (response && response.status === 200) {
          const copy = response.clone()
          caches.open(RUNTIME_CACHE).then((cache) => cache.put(request, copy)).catch(() => undefined)
        }
        return response
      })
      .catch(async () => {
        const cached = await caches.match(request)
        if (cached) return cached
        if (/\.(png|svg|ico)$/i.test(url.pathname)) {
          const fallbackIcon = await caches.match('/icon-192.png')
          if (fallbackIcon) return fallbackIcon
        }
        return Response.error()
      }),
  )
})
