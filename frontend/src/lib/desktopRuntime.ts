import { isTauriRuntime, resolveClientMode } from './clientMode'
import { recordRuntimeDiagnostic } from './runtimeDiagnostics'

type DesktopRuntimeKey = 'asr' | 'translation' | 'tts' | 'ffmpeg' | 'modelsRoot' | 'subtitleFont'

// Desktop runtime URLs used for browser-desktop mode (no Tauri).
const DESKTOP_RUNTIME_URLS: Record<DesktopRuntimeKey, string> = {
  asr: '/desktop-runtime/models/whisper-base.en',
  translation: '/desktop-runtime/models/m2m100_418M',
  tts: '/desktop-runtime/models/mms-tts-rus',
  ffmpeg: '/desktop-runtime/ffmpeg/esm',
  modelsRoot: '/desktop-runtime/models',
  subtitleFont: '/desktop-runtime/fonts/DejaVuSans.ttf',
}

const MODEL_NAMES: Record<Exclude<DesktopRuntimeKey, 'ffmpeg' | 'modelsRoot'>, string> = {
  asr: 'whisper-base.en',
  translation: 'm2m100_418M',
  tts: 'mms-tts-rus',
  subtitleFont: '../fonts/DejaVuSans.ttf',
}

// Cache the model server URL after the first Tauri command call.
let tauriModelServerUrl: string | null = null

async function getTauriModelServerUrl(): Promise<string> {
  if (tauriModelServerUrl !== null) return tauriModelServerUrl
  const { invoke } = await import('@tauri-apps/api/core')
  tauriModelServerUrl = await invoke<string>('get_model_server_url')
  return tauriModelServerUrl
}

export async function resolveDesktopRuntimeAssetUrl(key: DesktopRuntimeKey): Promise<string> {
  if (resolveClientMode() !== 'desktop' || typeof window === 'undefined') {
    return DESKTOP_RUNTIME_URLS[key]
  }
  if (!isTauriRuntime()) {
    return DESKTOP_RUNTIME_URLS[key]
  }

  // In packaged Tauri, models are served by a local HTTP server started at app
  // launch. The server streams files in chunks so large ONNX files (275–329 MB)
  // work without hitting WebKit custom-protocol buffer limits.
  if (key === 'ffmpeg') {
    return '/desktop-runtime/ffmpeg/esm'
  }

  const serverUrl = await getTauriModelServerUrl()
  const url =
    key === 'modelsRoot'
      ? `${serverUrl}/models`
      : key === 'subtitleFont'
        ? `${serverUrl}/fonts/DejaVuSans.ttf`
        : `${serverUrl}/models/${MODEL_NAMES[key]}`

  recordRuntimeDiagnostic('desktop.runtime', 'resolve.path', { key, url })
  return url
}
