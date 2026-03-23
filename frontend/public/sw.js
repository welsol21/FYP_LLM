const APP_SHELL_CACHE = 'ela-app-shell-v3'
const RUNTIME_CACHE = 'ela-runtime-v3'
const APP_SHELL_FILES = [
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
    caches.open(APP_SHELL_CACHE).then((cache) => cache.addAll(APP_SHELL_FILES)),
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
    ),
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

  const cacheableAsset = /\.(js|css|png|svg|ico|webmanifest|wasm)$/i.test(url.pathname)
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
        if (cached) {
          return cached
        }
        if (/\.(png|svg|ico)$/i.test(url.pathname)) {
          const fallbackIcon = await caches.match('/icon-192.png')
          if (fallbackIcon) return fallbackIcon
        }
        return Response.error()
      }
    ),
  )
})
