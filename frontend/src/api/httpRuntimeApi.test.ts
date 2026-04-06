import { beforeEach, describe, expect, it, vi } from 'vitest'
import { HttpRuntimeApi } from './httpRuntimeApi'
import { LocalWorkspace } from '../lib/localWorkspace'

describe('HttpRuntimeApi', () => {
  beforeEach(async () => {
    window.localStorage.clear()
    await LocalWorkspace.__resetForTests()
    const project = await LocalWorkspace.createProject('Demo Project')
    await LocalWorkspace.setSelectedProject(project.id)
    vi.restoreAllMocks()
  })

  it('_removed_upload_test_placeholder', async () => {
    // Tests for /api/upload backend flow were removed — upload path no longer exists.
    // All deployments use client-side Whisper; no media file is sent to the backend.
  })

  // Backend upload tests removed — /api/upload no longer exists.
  // All deployments use client-side Whisper; media files are never sent to backend.

  it('keeps file analysis flags in sync when analysis versions are deleted', async () => {
    const selected = await LocalWorkspace.getSelectedProject()
    const projectId = String(selected.project_id || '')
    expect(projectId).not.toBe('')

    const file = await LocalWorkspace.registerMediaFile({
      projectId,
      name: 'sync-test.mp3',
      mediaPath: '/uploads/sync-test.mp3',
      sizeBytes: 1024,
      durationSec: 10,
    })

    const contract = {
      'She came home.': {
        node_id: 's-1',
        type: 'Sentence',
        content: 'She came home.',
        tense: 'past',
        linguistic_notes: { elementary: '', intermediate: 'x', advanced: '' },
        part_of_speech: 'sentence',
        linguistic_elements: [],
        translations: { m2m100: { text: 'Она пришла домой.' } },
      },
    }

    await LocalWorkspace.upsertAnalysis({
      documentId: 'doc-old',
      projectId,
      mediaFileId: file.id,
      fileName: file.name,
      filePath: file.path || '',
      sizeBytes: file.size_bytes,
      durationSeconds: file.duration_seconds,
      settings: 'Transl: m2m100 / Subs: bilingual_sequential / Voice: male / Proc: incremental',
      contract,
    })
    await LocalWorkspace.upsertAnalysis({
      documentId: 'doc-new',
      projectId,
      mediaFileId: file.id,
      fileName: file.name,
      filePath: file.path || '',
      sizeBytes: file.size_bytes,
      durationSeconds: file.duration_seconds,
      settings: 'Transl: m2m100 / Subs: bilingual_simultaneous / Voice: female / Proc: force',
      contract,
    })

    let files = await LocalWorkspace.listFiles(projectId)
    let tracked = files.find((row) => row.id === file.id)
    expect(tracked?.analyzed).toBe(true)
    expect(tracked?.document_id).toBe('doc-new')

    await LocalWorkspace.deleteAnalysis('doc-new')
    files = await LocalWorkspace.listFiles(projectId)
    tracked = files.find((row) => row.id === file.id)
    expect(tracked?.analyzed).toBe(true)
    expect(tracked?.document_id).toBe('doc-old')

    await LocalWorkspace.deleteAnalysis('doc-old')
    files = await LocalWorkspace.listFiles(projectId)
    tracked = files.find((row) => row.id === file.id)
    expect(tracked?.analyzed).toBe(false)
    expect(tracked?.document_id).toBeUndefined()
    const history = await LocalWorkspace.listAnalysisHistory(projectId)
    expect(history.length).toBe(0)
  })

  it('keeps file analyzed when latest analysis row is contract_current=false but a valid contract exists', async () => {
    const selected = await LocalWorkspace.getSelectedProject()
    const projectId = String(selected.project_id || '')
    const file = await LocalWorkspace.registerMediaFile({
      projectId,
      name: 'current-contract-priority.mp3',
      mediaPath: '/uploads/current-contract-priority.mp3',
      sizeBytes: 1024,
      durationSec: 10,
    })

    const contract = {
      'She came home.': {
        node_id: 's-1',
        type: 'Sentence',
        content: 'She came home.',
        tense: 'past',
        linguistic_notes: { elementary: '', intermediate: 'x', advanced: '' },
        part_of_speech: 'sentence',
        linguistic_elements: [],
        translations: { m2m100: { text: 'Она пришла домой.' } },
      },
    }

    await LocalWorkspace.upsertAnalysis({
      documentId: 'doc-current',
      projectId,
      mediaFileId: file.id,
      fileName: file.name,
      filePath: file.path || '',
      sizeBytes: file.size_bytes,
      durationSeconds: file.duration_seconds,
      settings: 'Transl: m2m100 / Subs: bilingual_sequential / Voice: male / Proc: incremental',
      contract,
      contractCurrent: true,
    })

    await LocalWorkspace.upsertAnalysis({
      documentId: 'doc-staging',
      projectId,
      mediaFileId: file.id,
      fileName: file.name,
      filePath: file.path || '',
      sizeBytes: file.size_bytes,
      durationSeconds: file.duration_seconds,
      settings: 'Transl: m2m100 / Subs: bilingual_simultaneous / Voice: male / Proc: incremental',
      contract,
      contractCurrent: false,
    })

    const files = await LocalWorkspace.listFiles(projectId)
    const tracked = files.find((row) => row.id === file.id)
    expect(tracked?.analyzed).toBe(true)
    expect(tracked?.document_id).toBe('doc-current')
  })

  it('enriches visualizer payload with translations from other analysis versions of the same file', async () => {
    const selected = await LocalWorkspace.getSelectedProject()
    const projectId = String(selected.project_id || '')
    const file = await LocalWorkspace.registerMediaFile({
      projectId,
      name: 'providers-test.mp3',
      mediaPath: '/uploads/providers-test.mp3',
      sizeBytes: 128,
      durationSec: 3,
    })

    const baseContract = {
      'She came home.': {
        node_id: 's-1',
        type: 'Sentence',
        content: 'She came home.',
        tense: 'past',
        linguistic_notes: { elementary: '', intermediate: 'x', advanced: '' },
        part_of_speech: 'sentence',
        active_translation_provider: 'm2m100',
        linguistic_elements: [
          {
            node_id: 'w-1',
            type: 'Word',
            content: 'came',
            tense: 'past',
            linguistic_notes: { elementary: '', intermediate: 'x', advanced: '' },
            part_of_speech: 'verb',
            active_translation_provider: 'm2m100',
            linguistic_elements: [],
            translations: { m2m100: { text: 'пришла' } },
          },
        ],
        translations: { m2m100: { text: 'Она пришла домой.' } },
      },
    }

    const gptContract = {
      'She came home.': {
        node_id: 's-1',
        type: 'Sentence',
        content: 'She came home.',
        tense: 'past',
        linguistic_notes: { elementary: '', intermediate: 'x', advanced: '' },
        part_of_speech: 'sentence',
        active_translation_provider: 'gpt',
        linguistic_elements: [
          {
            node_id: 'w-1',
            type: 'Word',
            content: 'came',
            tense: 'past',
            linguistic_notes: { elementary: '', intermediate: 'x', advanced: '' },
            part_of_speech: 'verb',
            active_translation_provider: 'gpt',
            linguistic_elements: [],
            translations: { gpt: { text: 'вернулась' } },
          },
        ],
        translations: { gpt: { text: 'Она вернулась домой.' } },
      },
    }

    await LocalWorkspace.upsertAnalysis({
      documentId: 'doc-m2m100',
      projectId,
      mediaFileId: file.id,
      fileName: file.name,
      filePath: file.path || '',
      sizeBytes: file.size_bytes,
      durationSeconds: file.duration_seconds,
      settings: 'Transl: m2m100 / Subs: bilingual_sequential / Voice: male / Proc: incremental',
      contract: baseContract,
    })

    await LocalWorkspace.upsertAnalysis({
      documentId: 'doc-gpt',
      projectId,
      mediaFileId: file.id,
      fileName: file.name,
      filePath: file.path || '',
      sizeBytes: file.size_bytes,
      durationSeconds: file.duration_seconds,
      settings: 'Transl: gpt / Subs: bilingual_sequential / Voice: male / Proc: incremental',
      contract: gptContract,
    })

    const payload = await LocalWorkspace.getVisualizerPayload('doc-m2m100')
    const sentenceNode = payload['She came home.']
    expect(sentenceNode.translations.m2m100.text).toBe('Она пришла домой.')
    expect(sentenceNode.translations.gpt.text).toBe('Она вернулась домой.')
    expect(sentenceNode.active_translation_provider).toBe('m2m100')
    expect(sentenceNode.linguistic_elements[0].translations.m2m100.text).toBe('пришла')
    expect(sentenceNode.linguistic_elements[0].translations.gpt.text).toBe('вернулась')
  })

  it('deletes project with cascade cleanup for files and analyses', async () => {
    const first = await LocalWorkspace.getSelectedProject()
    const keepProjectId = String(first.project_id || '')
    const extra = await LocalWorkspace.createProject('Project To Delete')
    await LocalWorkspace.setSelectedProject(extra.id)
    const file = await LocalWorkspace.registerMediaFile({
      projectId: extra.id,
      name: 'delete-me.mp3',
      mediaPath: '/client-media/delete-me.mp3',
      sizeBytes: 10,
      durationSec: 1,
    })
    await LocalWorkspace.upsertAnalysis({
      documentId: 'doc-delete-project',
      projectId: extra.id,
      mediaFileId: file.id,
      fileName: file.name,
      filePath: file.path || '',
      sizeBytes: file.size_bytes,
      durationSeconds: file.duration_seconds,
      settings: 'Transl: m2m100 / Subs: bilingual_simultaneous / Voice: female / Proc: force',
      contract: {},
      artifacts: [],
      contractCurrent: false,
    })

    const deleted = await LocalWorkspace.deleteProject(extra.id)
    expect(deleted.status).toBe('ok')

    const projects = await LocalWorkspace.listProjects()
    expect(projects.some((p) => p.id === extra.id)).toBe(false)

    const files = await LocalWorkspace.listFiles(extra.id)
    expect(files.length).toBe(0)

    const history = await LocalWorkspace.listAnalysisHistory(extra.id)
    expect(history.length).toBe(0)

    const selected = await LocalWorkspace.getSelectedProject()
    expect(String(selected.project_id || '')).not.toBe(extra.id)
    expect(String(selected.project_id || '')).not.toBe('')
    expect(projects.some((p) => p.id === keepProjectId)).toBe(true)
  })

  // 'fails with clear error when backend upload returns 404' removed — /api/upload no longer exists.

  it('exposes cached translated media artifacts for audio analyses', async () => {
    const selected = await LocalWorkspace.getSelectedProject()
    const projectId = String(selected.project_id || '')
    const mediaPath = '/client-media/audio-case/sample.mp3'
    await LocalWorkspace.cacheUploadedMedia(mediaPath, new Blob([new Uint8Array([1, 2, 3, 4, 5])], { type: 'audio/mpeg' }))
    const file = await LocalWorkspace.registerMediaFile({
      projectId,
      name: 'sample.mp3',
      mediaPath,
      sizeBytes: 5,
      durationSec: 1,
    })
    await LocalWorkspace.upsertAnalysis({
      documentId: 'doc-audio-fallback',
      projectId,
      mediaFileId: file.id,
      fileName: file.name,
      filePath: mediaPath,
      sizeBytes: 5,
      durationSeconds: 1,
      settings: 'Transl: m2m100 / Subs: bilingual_simultaneous / Voice: female / Proc: force',
      contract: {},
      artifacts: [
        {
          name: 'full_text.txt',
          size_bytes: 3,
          download_url: 'data:text/plain;charset=utf-8,abc',
        },
      ],
      contractCurrent: false,
    })
    await LocalWorkspace.cacheAnalysisArtifactBlob(
      'doc-audio-fallback',
      'translated_audio_ru.mp3',
      new Blob([new Uint8Array([1, 2, 3, 4])], { type: 'audio/mpeg' }),
    )
    await LocalWorkspace.cacheAnalysisArtifactBlob(
      'doc-audio-fallback',
      'translated_video_ru.mp4',
      new Blob([new Uint8Array([9, 8, 7, 6])], { type: 'video/mp4' }),
    )
    const artifacts = await LocalWorkspace.listDocumentArtifacts('doc-audio-fallback')
    const translatedVideo = artifacts.find((a) => a.name === 'translated_video_ru.mp4')
    const translatedAudio = artifacts.find((a) => a.name === 'translated_audio_ru.mp3')
    expect(translatedAudio).toBeDefined()
    expect(Number(translatedAudio?.size_bytes || 0)).toBeGreaterThan(0)
    expect(String(translatedAudio?.download_url || '')).not.toBe('')
    expect(translatedVideo).toBeDefined()
    expect(Number(translatedVideo?.size_bytes || 0)).toBeGreaterThan(0)
    expect(String(translatedVideo?.download_url || '')).not.toBe('')
  })

  it('exposes non-empty translated_video artifact for video analyses', async () => {
    const selected = await LocalWorkspace.getSelectedProject()
    const projectId = String(selected.project_id || '')
    const mediaPath = '/client-media/video-case/sample.mp4'
    await LocalWorkspace.cacheUploadedMedia(mediaPath, new Blob([new Uint8Array([1, 2, 3, 4, 5, 6])], { type: 'video/mp4' }))
    const file = await LocalWorkspace.registerMediaFile({
      projectId,
      name: 'sample.mp4',
      mediaPath,
      sizeBytes: 6,
      durationSec: 1,
    })
    await LocalWorkspace.upsertAnalysis({
      documentId: 'doc-video',
      projectId,
      mediaFileId: file.id,
      fileName: file.name,
      filePath: mediaPath,
      sizeBytes: 6,
      durationSeconds: 1,
      settings: 'Transl: m2m100 / Subs: bilingual_simultaneous / Voice: female / Proc: force',
      contract: {},
      artifacts: [
        {
          name: 'full_text.txt',
          size_bytes: 3,
          download_url: 'data:text/plain;charset=utf-8,abc',
        },
      ],
      contractCurrent: false,
    })
    await LocalWorkspace.cacheAnalysisArtifactBlob(
      'doc-video',
      'translated_video_ru.mp4',
      new Blob([new Uint8Array([1, 2, 3, 4, 5, 6, 7])], { type: 'video/mp4' }),
    )
    const artifacts = await LocalWorkspace.listDocumentArtifacts('doc-video')
    const translatedVideo = artifacts.find((a) => a.name === 'translated_video_ru.mp4')
    expect(translatedVideo).toBeDefined()
    expect(Number(translatedVideo?.size_bytes || 0)).toBeGreaterThan(0)
    expect(String(translatedVideo?.download_url || '')).not.toBe('')
  })

  it('routes DeepL provider translation through browser API (not backend /api/translate)', async () => {
    const api = new HttpRuntimeApi()
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ translations: [{ text: 'Привет' }] }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )

    const out = await (api as unknown as {
      _clientTranslateTextsWithProvider: (
        provider: string,
        texts: string[],
        credentials: Record<string, string>,
        onProgress: (done: number, total: number) => void,
      ) => Promise<Record<string, string>>
    })._clientTranslateTextsWithProvider(
      'deepl',
      ['Hello'],
      { auth_key: 'test-auth-key:fx' },
      () => {},
    )

    expect(out.Hello).toBe('Привет')
    expect(fetchSpy).toHaveBeenCalledTimes(1)
    expect(String(fetchSpy.mock.calls[0][0])).toContain('api-free.deepl.com')
    expect(String(fetchSpy.mock.calls[0][0])).not.toContain('/api/translate')
  })

  it('routes OpenAI provider translation through browser API (not backend /api/translate)', async () => {
    const api = new HttpRuntimeApi()
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          choices: [{ message: { content: JSON.stringify({ translations: ['Здравствуйте'] }) } }],
        }),
        {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        },
      ),
    )

    const out = await (api as unknown as {
      _clientTranslateTextsWithProvider: (
        provider: string,
        texts: string[],
        credentials: Record<string, string>,
        onProgress: (done: number, total: number) => void,
      ) => Promise<Record<string, string>>
    })._clientTranslateTextsWithProvider(
      'gpt',
      ['Hello'],
      { api_key: 'test-openai-key' },
      () => {},
    )

    expect(out.Hello).toBe('Здравствуйте')
    expect(fetchSpy).toHaveBeenCalledTimes(1)
    expect(String(fetchSpy.mock.calls[0][0])).toContain('api.openai.com/v1/chat/completions')
    expect(String(fetchSpy.mock.calls[0][0])).not.toContain('/api/translate')
  })

  it('parses Lara batch translation when payload is nested as JSON string in data.content', async () => {
    const api = new HttpRuntimeApi()
    vi.spyOn(api as unknown as { _clientLaraAuthToken: (...args: unknown[]) => Promise<string> }, '_clientLaraAuthToken')
      .mockResolvedValue('test-token')
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          data: {
            content: JSON.stringify({ translations: ['Привет', 'Пока'] }),
          },
        }),
        {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        },
      ),
    )

    const out = await (api as unknown as {
      _clientTranslateTextsWithProvider: (
        provider: string,
        texts: string[],
        credentials: Record<string, string>,
        onProgress: (done: number, total: number) => void,
      ) => Promise<Record<string, string>>
    })._clientTranslateTextsWithProvider(
      'lara',
      ['Hello', 'Bye'],
      { api_id: 'test-id', api_secret: 'test-secret' },
      () => {},
    )

    expect(out.Hello).toBe('Привет')
    expect(out.Bye).toBe('Пока')
    expect(fetchSpy).toHaveBeenCalledTimes(1)
  })

  it('falls back to Lara single translations when batch response shape is invalid', async () => {
    const api = new HttpRuntimeApi()
    vi.spyOn(api as unknown as { _clientLaraAuthToken: (...args: unknown[]) => Promise<string> }, '_clientLaraAuthToken')
      .mockResolvedValue('test-token')
    const fetchSpy = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ data: { unexpected: true } }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ translation: 'Привет' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ translation: 'Пока' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      )

    const out = await (api as unknown as {
      _clientTranslateTextsWithProvider: (
        provider: string,
        texts: string[],
        credentials: Record<string, string>,
        onProgress: (done: number, total: number) => void,
      ) => Promise<Record<string, string>>
    })._clientTranslateTextsWithProvider(
      'lara',
      ['Hello', 'Bye'],
      { api_id: 'test-id', api_secret: 'test-secret' },
      () => {},
    )

    expect(out.Hello).toBe('Привет')
    expect(out.Bye).toBe('Пока')
    expect(fetchSpy).toHaveBeenCalledTimes(3)
  })
})
