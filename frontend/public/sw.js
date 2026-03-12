const APP_SHELL_CACHE = 'ela-app-shell-v1'
const RUNTIME_CACHE = 'ela-runtime-v1'
const APP_SHELL_FILES = [
  '/',
  '/index.html',
  '/manifest.webmanifest',
  '/offline.html',
  '/icon-192.png',
  '/icon-512.png',
  '/icon-maskable-192.png',
  '/icon-maskable-512.png',
  '/apple-touch-icon.png',
]

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(APP_SHELL_CACHE).then((cache) => cache.addAll(APP_SHELL_FILES)).then(() => self.skipWaiting()),
  )
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key !== APP_SHELL_CACHE && key !== RUNTIME_CACHE)
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
      fetch(request)
        .then((response) => {
          const copy = response.clone()
          caches.open(RUNTIME_CACHE).then((cache) => cache.put('/index.html', copy)).catch(() => undefined)
          return response
        })
        .catch(async () => {
          const cached = await caches.match('/index.html')
          return cached || caches.match('/offline.html')
        }),
    )
    return
  }

  if (!isSameOrigin) return

  const cacheableAsset = /\.(js|css|png|svg|ico|webmanifest|wasm)$/i.test(url.pathname)
  if (!cacheableAsset) return

  event.respondWith(
    caches.match(request).then(async (cached) => {
      if (cached) {
        fetch(request)
          .then((response) => {
            if (!response || response.status !== 200) return
            caches.open(RUNTIME_CACHE).then((cache) => cache.put(request, response)).catch(() => undefined)
          })
          .catch(() => undefined)
        return cached
      }
      const response = await fetch(request)
      if (response && response.status === 200) {
        const copy = response.clone()
        caches.open(RUNTIME_CACHE).then((cache) => cache.put(request, copy)).catch(() => undefined)
      }
      return response
    }),
  )
})
