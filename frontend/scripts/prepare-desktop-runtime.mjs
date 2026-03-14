import { cpSync, existsSync, mkdirSync, rmSync, writeFileSync } from 'node:fs'
import path from 'node:path'

const frontendRoot = process.cwd()
const publicRoot = path.join(frontendRoot, 'public')
const runtimeRoot = path.join(publicRoot, 'desktop-runtime')
const ffmpegSource = path.join(frontendRoot, 'node_modules', '@ffmpeg', 'core', 'dist', 'esm')
const ffmpegTarget = path.join(runtimeRoot, 'ffmpeg', 'esm')
const translationSource = path.resolve(frontendRoot, '..', 'artifacts', 'models', 'm2m100_418M')
const translationTarget = path.join(runtimeRoot, 'models', 'm2m100_418M')
const asrSource = path.resolve(frontendRoot, '..', 'artifacts', 'models', 'whisper-base.en')
const asrTarget = path.join(runtimeRoot, 'models', 'whisper-base.en')
const ttsSource = path.resolve(frontendRoot, '..', 'artifacts', 'models', 'mms-tts-rus')
const ttsTarget = path.join(runtimeRoot, 'models', 'mms-tts-rus')
const manifestPath = path.join(runtimeRoot, 'manifest.json')

rmSync(runtimeRoot, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 })
mkdirSync(runtimeRoot, { recursive: true })

if (!existsSync(ffmpegSource)) {
  throw new Error(`FFmpeg core not found: ${ffmpegSource}`)
}
mkdirSync(path.dirname(ffmpegTarget), { recursive: true })
cpSync(ffmpegSource, ffmpegTarget, { recursive: true })

const manifest = {
  prepared_at: new Date().toISOString(),
  ffmpeg: {
    source: ffmpegSource,
    target: ffmpegTarget,
    included: true,
  },
  translation: {
    source: translationSource,
    target: translationTarget,
    included: false,
  },
  asr: {
    source: asrSource,
    target: asrTarget,
    included: false,
  },
  tts: {
    source: ttsSource,
    target: ttsTarget,
    included: false,
  },
}

if (existsSync(translationSource)) {
  mkdirSync(path.dirname(translationTarget), { recursive: true })
  cpSync(translationSource, translationTarget, { recursive: true })
  manifest.translation.included = true
}

if (existsSync(asrSource)) {
  mkdirSync(path.dirname(asrTarget), { recursive: true })
  cpSync(asrSource, asrTarget, { recursive: true })
  manifest.asr.included = true
} else {
  manifest.asr.reason = 'Local ASR model files are not present on disk yet.'
}

if (existsSync(ttsSource)) {
  mkdirSync(path.dirname(ttsTarget), { recursive: true })
  cpSync(ttsSource, ttsTarget, { recursive: true })
  manifest.tts.included = true
} else {
  manifest.tts.reason = 'Local TTS model files are not present on disk yet.'
}

writeFileSync(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, 'utf8')
console.log(`Prepared desktop runtime assets in ${runtimeRoot}`)
