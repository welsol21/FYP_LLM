/**
 * Translation WebWorker — runs Xenova/opus-mt-en-ru in a background thread.
 *
 * Message protocol (main → worker):
 *   { type: 'translate', id: string, sentences: string[] }
 *
 * Message protocol (worker → main):
 *   { type: 'progress', loaded: number, total: number }
 *   { type: 'result', id: string, index: number, total: number, text: string }
 *   { type: 'done', id: string }
 *   { type: 'error', id: string, message: string }
 */

/* eslint-disable @typescript-eslint/no-explicit-any */
import { pipeline, env } from '@huggingface/transformers'

;(env as any).allowLocalModels = false

let translator: any = null

async function getTranslator(): Promise<any> {
  if (translator) return translator
  translator = await (pipeline as any)('translation', 'Xenova/opus-mt-en-ru', {
    dtype: 'q8',
    progress_callback: (info: any) => {
      if (typeof info?.progress === 'number') {
        self.postMessage({ type: 'progress', loaded: Math.round(info.progress as number), total: 100 })
      }
    },
  })
  return translator
}

self.addEventListener('message', async (event: MessageEvent) => {
  const { type, id, sentences } = event.data as { type: string; id: string; sentences: string[] }
  if (type !== 'translate') return
  try {
    const t = await getTranslator()
    const total = sentences.length
    for (let index = 0; index < total; index += 1) {
      const sentence = sentences[index]
      const output: any = await t(sentence, { src_lang: 'en', tgt_lang: 'ru' })
      const text = String(
        (Array.isArray(output) ? (output[0] as any)?.translation_text : '') || '',
      ).trim()
      self.postMessage({ type: 'result', id, index, total, text })
    }
    self.postMessage({ type: 'done', id })
  } catch (err) {
    self.postMessage({ type: 'error', id, message: err instanceof Error ? err.message : String(err) })
  }
})
