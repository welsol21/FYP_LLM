import { cpSync, existsSync, mkdirSync, rmSync, writeFileSync } from 'node:fs'
import path from 'node:path'

const frontendRoot = process.cwd()
const targetMode = process.argv.includes('--bundle') ? 'bundle' : 'dev'
const publicRuntimeRoot = path.join(frontendRoot, 'public', 'desktop-runtime')
const tauriRuntimeRoot = path.join(frontendRoot, 'src-tauri', 'resources', 'desktop-runtime')
const modelsRoot = targetMode === 'bundle' ? tauriRuntimeRoot : publicRuntimeRoot
const ffmpegSource = path.join(frontendRoot, 'node_modules', '@ffmpeg', 'core', 'dist', 'esm')
const ffmpegTarget = path.join(publicRuntimeRoot, 'ffmpeg', 'esm')
const translationSource = path.resolve(frontendRoot, '..', 'artifacts', 'models', 'm2m100_418M')
const translationTarget = path.join(modelsRoot, 'models', 'm2m100_418M')
const asrSource = path.resolve(frontendRoot, '..', 'artifacts', 'models', 'whisper-base.en')
const asrTarget = path.join(modelsRoot, 'models', 'whisper-base.en')
const ttsSource = path.resolve(frontendRoot, '..', 'artifacts', 'models', 'mms-tts-rus')
const ttsTarget = path.join(modelsRoot, 'models', 'mms-tts-rus')
const manifestPath = path.join(publicRuntimeRoot, 'manifest.json')

rmSync(publicRuntimeRoot, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 })
if (targetMode === 'bundle') {
  rmSync(path.join(tauriRuntimeRoot, 'models'), { recursive: true, force: true, maxRetries: 5, retryDelay: 100 })
}
mkdirSync(publicRuntimeRoot, { recursive: true })
if (targetMode === 'bundle') {
  mkdirSync(path.join(tauriRuntimeRoot, 'models'), { recursive: true })
}

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
  // transformers.js v3 requires preprocessor_config.json for VitsProcessor.
  // This file is absent from the facebook/mms-tts-* HuggingFace repos, so we
  // synthesise a minimal one if the source directory does not already contain it.
  const preprocessorTarget = path.join(ttsTarget, 'preprocessor_config.json')
  const preprocessorSource = path.join(ttsSource, 'preprocessor_config.json')
  if (!existsSync(preprocessorSource)) {
    writeFileSync(preprocessorTarget, '{\n  "processor_class": "VitsProcessor"\n}\n', 'utf8')
  }
  manifest.tts.included = true
} else {
  manifest.tts.reason = 'Local TTS model files are not present on disk yet.'
}

writeFileSync(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, 'utf8')
console.log(`[prepare-desktop-runtime] mode=${targetMode}`)
console.log(`[prepare-desktop-runtime] publicRoot=${publicRuntimeRoot}`)
console.log(`[prepare-desktop-runtime] modelsRoot=${modelsRoot}`)
console.log(`[prepare-desktop-runtime] ffmpeg included=${manifest.ffmpeg.included}`)
console.log(`[prepare-desktop-runtime] translation included=${manifest.translation.included}`)
console.log(`[prepare-desktop-runtime] asr included=${manifest.asr.included}`)
console.log(`[prepare-desktop-runtime] tts included=${manifest.tts.included}`)
