import { resolveResource } from '@tauri-apps/api/path'

import { resolveClientMode } from './clientMode'
import { recordRuntimeDiagnostic } from './runtimeDiagnostics'

type DesktopRuntimeKey = 'asr' | 'translation' | 'tts' | 'ffmpeg' | 'modelsRoot'

const DESKTOP_RUNTIME_RELATIVE_PATHS: Record<DesktopRuntimeKey, string> = {
  asr: 'desktop-runtime/models/whisper-base.en',
  translation: 'desktop-runtime/models/m2m100_418M',
  tts: 'desktop-runtime/models/mms-tts-rus',
  ffmpeg: 'desktop-runtime/ffmpeg/esm',
  modelsRoot: 'desktop-runtime/models',
}

let resolvedPathsPromise: Promise<Record<DesktopRuntimeKey, string>> | null = null

function envFallback(key: DesktopRuntimeKey): string {
  if (key === 'asr') return '/desktop-runtime/models/whisper-base.en'
  if (key === 'translation') return '/desktop-runtime/models/m2m100_418M'
  if (key === 'tts') return '/desktop-runtime/models/mms-tts-rus'
  if (key === 'modelsRoot') return '/desktop-runtime/models'
  return '/desktop-runtime/ffmpeg/esm'
}

// convertFileSrc encodes ALL slashes as %2F, which breaks transformers.js
// (it appends filenames with literal slashes, creating mixed-encoding URLs).
// We build the asset URL manually: encode each path component, keep slashes as separators.
function buildProperAssetUrl(filesystemPath: string): string {
  return 'asset://localhost' + filesystemPath.split('/').map(encodeURIComponent).join('/')
}

function normalizeTauriLinuxResourcePath(filePath: string): string {
  const raw = String(filePath || '').trim()
  if (!raw) return raw
  if (raw.includes('/resources/')) return raw
  // Tauri DEB resolveResource returns /usr/lib/{productName}/{relativePath}
  // but files are actually installed at /usr/lib/{productName}/resources/{relativePath}
  const m = raw.match(/^(\/usr\/lib\/[^/]+\/)(.+)$/)
  if (m) return m[1] + 'resources/' + m[2]
  return raw
}

async function resolveDesktopRuntimePaths(): Promise<Record<DesktopRuntimeKey, string>> {
  if (resolveClientMode() !== 'desktop' || typeof window === 'undefined') {
    return {
      asr: envFallback('asr'),
      translation: envFallback('translation'),
      tts: envFallback('tts'),
      ffmpeg: envFallback('ffmpeg'),
      modelsRoot: envFallback('modelsRoot'),
    }
  }

  if (!resolvedPathsPromise) {
    resolvedPathsPromise = (async () => {
      recordRuntimeDiagnostic('desktop.runtime', 'resolve.start')
      try {
        const entries = await Promise.all(
          Object.entries(DESKTOP_RUNTIME_RELATIVE_PATHS).map(async ([key, relativePath]) => {
            const resolvedFilePath = await resolveResource(relativePath)
            const filePath = normalizeTauriLinuxResourcePath(resolvedFilePath)
            const assetUrl = buildProperAssetUrl(filePath)
            recordRuntimeDiagnostic('desktop.runtime', 'resolve.path', {
              key,
              relativePath,
              resolvedFilePath,
              filePath,
              assetUrl,
            })
            return [key, assetUrl] as const
          }),
        )
        recordRuntimeDiagnostic('desktop.runtime', 'resolve.ready')
        return Object.fromEntries(entries) as Record<DesktopRuntimeKey, string>
      } catch (error) {
        recordRuntimeDiagnostic('desktop.runtime', 'resolve.fallback', error, 'warning')
        return {
          asr: envFallback('asr'),
          translation: envFallback('translation'),
          tts: envFallback('tts'),
          ffmpeg: envFallback('ffmpeg'),
          modelsRoot: envFallback('modelsRoot'),
        }
      }
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
