import { convertFileSrc } from '@tauri-apps/api/core'
import { resolveResource } from '@tauri-apps/api/path'

import { resolveClientMode } from './clientMode'
import { recordRuntimeDiagnostic } from './runtimeDiagnostics'

type DesktopRuntimeKey = 'asr' | 'translation' | 'tts' | 'ffmpeg'

const DESKTOP_RUNTIME_RELATIVE_PATHS: Record<DesktopRuntimeKey, string> = {
  asr: 'desktop-runtime/models/whisper-base.en',
  translation: 'desktop-runtime/models/m2m100_418M',
  tts: 'desktop-runtime/models/mms-tts-rus',
  ffmpeg: 'desktop-runtime/ffmpeg/esm',
}

let resolvedPathsPromise: Promise<Record<DesktopRuntimeKey, string>> | null = null

function envFallback(key: DesktopRuntimeKey): string {
  if (key === 'asr') return '/desktop-runtime/models/whisper-base.en'
  if (key === 'translation') return '/desktop-runtime/models/m2m100_418M'
  if (key === 'tts') return '/desktop-runtime/models/mms-tts-rus'
  return '/desktop-runtime/ffmpeg/esm'
}

async function resolveDesktopRuntimePaths(): Promise<Record<DesktopRuntimeKey, string>> {
  if (resolveClientMode() !== 'desktop' || typeof window === 'undefined' || !('__TAURI__' in window)) {
    return {
      asr: envFallback('asr'),
      translation: envFallback('translation'),
      tts: envFallback('tts'),
      ffmpeg: envFallback('ffmpeg'),
    }
  }

  if (!resolvedPathsPromise) {
    resolvedPathsPromise = (async () => {
      recordRuntimeDiagnostic('desktop.runtime', 'resolve.start')
      const entries = await Promise.all(
        Object.entries(DESKTOP_RUNTIME_RELATIVE_PATHS).map(async ([key, relativePath]) => {
          const filePath = await resolveResource(relativePath)
          const assetUrl = convertFileSrc(filePath)
          recordRuntimeDiagnostic('desktop.runtime', 'resolve.path', {
            key,
            relativePath,
            filePath,
            assetUrl,
          })
          return [key, assetUrl] as const
        }),
      )
      recordRuntimeDiagnostic('desktop.runtime', 'resolve.ready')
      return Object.fromEntries(entries) as Record<DesktopRuntimeKey, string>
    })().catch((error) => {
      resolvedPathsPromise = null
      recordRuntimeDiagnostic('desktop.runtime', 'resolve.error', error, 'error')
      throw error
    })
  }

  return resolvedPathsPromise
}

export async function resolveDesktopRuntimeAssetUrl(key: DesktopRuntimeKey): Promise<string> {
  const paths = await resolveDesktopRuntimePaths()
  return paths[key]
}
