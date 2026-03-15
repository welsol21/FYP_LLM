function normalizedApiBaseUrl(): string {
  const raw = String(import.meta.env?.VITE_API_BASE_URL || '').trim()
  if (!raw) return ''
  return raw.replace(/\/+$/, '')
}

export function apiUrl(path: string): string {
  if (/^(https?:|data:|blob:)/i.test(path)) return path
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  const base = normalizedApiBaseUrl()
  return base ? `${base}${normalizedPath}` : normalizedPath
}

export async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(apiUrl(url), init)
  const contentType = String(res.headers.get('content-type') || '').toLowerCase()
  const text = await res.text()
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}: ${text}`)
  }
  if (!contentType.includes('application/json')) {
    const preview = text.slice(0, 160).trim()
    throw new Error(`Non-JSON response from ${url}: ${preview || '(empty response)'}`)
  }
  try {
    return JSON.parse(text) as T
  } catch (error) {
    const preview = text.slice(0, 160).trim()
    throw new Error(`Invalid JSON response from ${url}: ${preview || (error instanceof Error ? error.message : 'unknown parse error')}`)
  }
}

export async function requestBlob(url: string, init?: RequestInit): Promise<Blob> {
  const res = await fetch(apiUrl(url), init)
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`HTTP ${res.status}: ${text}`)
  }
  return normalizeBlobLike(await res.blob())
}

export function shouldRetryBackendRequest(status: number): boolean {
  return status === 502 || status === 503 || status === 504
}

export async function sleepMs(ms: number): Promise<void> {
  await new Promise<void>((resolve) => window.setTimeout(resolve, ms))
}

export async function fetchWithRetry(
  input: string,
  init: RequestInit,
  options?: { retries?: number; retryDelayMs?: number },
): Promise<Response> {
  const retries = Math.max(0, options?.retries ?? 1)
  const retryDelayMs = Math.max(0, options?.retryDelayMs ?? 1200)
  let lastError: unknown = null
  for (let attempt = 0; attempt <= retries; attempt += 1) {
    try {
      const res = await fetch(apiUrl(input), init)
      if (!shouldRetryBackendRequest(res.status) || attempt >= retries) return res
      lastError = new Error(`HTTP ${res.status}`)
    } catch (error) {
      lastError = error
      if (attempt >= retries) throw error
    }
    await sleepMs(retryDelayMs)
  }
  throw lastError instanceof Error ? lastError : new Error('Backend request failed.')
}

export async function normalizeBlobLike(value: unknown): Promise<Blob> {
  if (value instanceof Blob) return value
  if (value && typeof (value as { arrayBuffer?: unknown }).arrayBuffer === 'function') {
    const blobLike = value as { arrayBuffer: () => Promise<ArrayBuffer>; type?: string }
    return new Blob([await blobLike.arrayBuffer()], { type: String(blobLike.type || '') })
  }
  return new Blob([value == null ? '' : String(value)])
}

export async function blobToDataUrl(blob: Blob): Promise<string> {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    reader.onerror = () => reject(reader.error || new Error('Failed to read blob.'))
    reader.onload = () => resolve(String(reader.result || ''))
    normalizeBlobLike(blob)
      .then((normalized) => reader.readAsDataURL(normalized))
      .catch(reject)
  })
}
