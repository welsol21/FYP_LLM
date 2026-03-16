import { isTauriRuntime, resolveClientMode } from './clientMode'
import { recordRuntimeDiagnostic } from './runtimeDiagnostics'

type DesktopRuntimeKey = 'asr' | 'translation' | 'tts' | 'ffmpeg' | 'modelsRoot'

// Desktop runtime stays inside the bundled web assets so browser-desktop and
// packaged Tauri desktop resolve the same URLs.
const DESKTOP_RUNTIME_URLS: Record<DesktopRuntimeKey, string> = {
  asr: '/desktop-runtime/models/whisper-base.en',
  translation: '/desktop-runtime/models/m2m100_418M',
  tts: '/desktop-runtime/models/mms-tts-rus',
  ffmpeg: '/desktop-runtime/ffmpeg/esm',
  modelsRoot: '/desktop-runtime/models',
}

// In a packaged Tauri app, models are served via the model:// custom protocol
// (Tauri external resources, not embedded in the binary).
const TAURI_RUNTIME_URLS: Record<DesktopRuntimeKey, string> = {
  asr: 'model://localhost/models/whisper-base.en',
  translation: 'model://localhost/models/m2m100_418M',
  tts: 'model://localhost/models/mms-tts-rus',
  ffmpeg: '/desktop-runtime/ffmpeg/esm',
  modelsRoot: 'model://localhost/models',
}

export async function resolveDesktopRuntimeAssetUrl(key: DesktopRuntimeKey): Promise<string> {
  if (resolveClientMode() !== 'desktop' || typeof window === 'undefined') {
    return DESKTOP_RUNTIME_URLS[key]
  }
  const url = isTauriRuntime() ? TAURI_RUNTIME_URLS[key] : DESKTOP_RUNTIME_URLS[key]
  recordRuntimeDiagnostic('desktop.runtime', 'resolve.path', { key, url })
  return url
}
