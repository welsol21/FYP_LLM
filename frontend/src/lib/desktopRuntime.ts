import { resolveClientMode } from './clientMode'
import { recordRuntimeDiagnostic } from './runtimeDiagnostics'

type DesktopRuntimeKey = 'asr' | 'translation' | 'tts' | 'ffmpeg' | 'modelsRoot'

// model:// is a custom Tauri protocol registered in src-tauri/src/lib.rs.
// It serves files directly from the app resource directory without any
// scope/glob/encoding restrictions that plagued the asset:// protocol.
// URL format: model://localhost/<path-relative-to-resources-dir>
const MODEL_PROTOCOL_URLS: Record<DesktopRuntimeKey, string> = {
  asr: 'model://localhost/desktop-runtime/models/whisper-base.en',
  translation: 'model://localhost/desktop-runtime/models/m2m100_418M',
  tts: 'model://localhost/desktop-runtime/models/mms-tts-rus',
  ffmpeg: 'model://localhost/desktop-runtime/ffmpeg/esm',
  modelsRoot: 'model://localhost/desktop-runtime/models',
}

// Fallback for non-desktop (PWA) mode — relative HTTP paths served by Vite/SW
const HTTP_FALLBACK_URLS: Record<DesktopRuntimeKey, string> = {
  asr: '/desktop-runtime/models/whisper-base.en',
  translation: '/desktop-runtime/models/m2m100_418M',
  tts: '/desktop-runtime/models/mms-tts-rus',
  ffmpeg: '/desktop-runtime/ffmpeg/esm',
  modelsRoot: '/desktop-runtime/models',
}

export async function resolveDesktopRuntimeAssetUrl(key: DesktopRuntimeKey): Promise<string> {
  if (resolveClientMode() !== 'desktop' || typeof window === 'undefined') {
    return HTTP_FALLBACK_URLS[key]
  }
  const url = MODEL_PROTOCOL_URLS[key]
  recordRuntimeDiagnostic('desktop.runtime', 'resolve.path', { key, url })
  return url
}

