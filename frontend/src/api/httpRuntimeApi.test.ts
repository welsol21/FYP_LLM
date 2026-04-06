import { beforeEach, describe, expect, it, vi } from 'vitest'
import { HttpRuntimeApi } from './httpRuntimeApi'
import { LocalWorkspace } from '../lib/localWorkspace'

describe('HttpRuntimeApi', () => {
  async function hashHex(input: string): Promise<string> {
    const buf = await globalThis.crypto.subtle.digest('SHA-256', new TextEncoder().encode(input))
    return Array.from(new Uint8Array(buf)).map((b) => b.toString(16).padStart(2, '0')).join('')
  }

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

  it('migrates legacy camelCase workspace fields on reload without losing providers or file links', async () => {
    await LocalWorkspace.__resetForTests()
    const legacyState = {
      projects: [
        {
          id: 'proj-legacy',
          name: 'Legacy Project',
          createdAt: '2026-04-01T10:00:00.000Z',
          updatedAt: '2026-04-01T10:05:00.000Z',
        },
      ],
      selectedProjectId: 'proj-legacy',
      files: [
        {
          id: 'file-legacy-1',
          projectId: 'proj-legacy',
          name: 'legacy.mp3',
          mediaPath: '/client-media/legacy/legacy.mp3',
          sizeBytes: 1234,
          durationSec: 5,
          settings: 'Transl: deepl / Subs: bilingual_sequential / Voice: male / Proc: incremental',
          updatedAt: '2026-04-01T10:05:00.000Z',
          createdAt: '2026-04-01T10:00:00.000Z',
          analyzed: true,
          documentId: 'doc-legacy-1',
        },
      ],
      analyses: [
        {
          analysisId: 'doc-legacy-1',
          documentId: 'doc-legacy-1',
          projectId: 'proj-legacy',
          projectName: 'Legacy Project',
          mediaFileId: 'file-legacy-1',
          fileName: 'legacy.mp3',
          filePath: '/client-media/legacy/legacy.mp3',
          settings: 'Transl: deepl / Subs: bilingual_sequential / Voice: male / Proc: incremental',
          itemsCount: 1,
          contractCurrent: true,
          updatedAt: '2026-04-01T10:05:00.000Z',
          createdAt: '2026-04-01T10:00:00.000Z',
          contract: {
            'Legacy sentence.': {
              node_id: 'n-1',
              type: 'sentence',
              content: 'Legacy sentence.',
              tense: '',
              linguistic_notes: { elementary: '', intermediate: '', advanced: '' },
              part_of_speech: 'sentence',
              linguistic_elements: [],
              translations: { deepl: { text: 'Легаси предложение.' } },
            },
          },
          artifacts: [],
        },
      ],
      translationConfig: {
        defaultProvider: 'deepl',
        providers: [
          { id: 'm2m100', label: 'M2M100', kind: 'builtin', enabled: true, credentialFields: [], credentials: {} },
          { id: 'deepl', label: 'DeepL', kind: 'builtin', enabled: true, credentialFields: ['auth_key'], credentials: { auth_key: 'k' } },
          { id: 'gpt', label: 'OpenAI GPT', kind: 'builtin', enabled: true, credentialFields: ['api_key'], credentials: { api_key: 'g' } },
        ],
      },
    }
    window.localStorage.setItem('ela_frontend_workspace_v1', JSON.stringify(legacyState))

    const projects = await LocalWorkspace.listProjects()
    expect(projects.some((row) => row.id === 'proj-legacy')).toBe(true)

    const files = await LocalWorkspace.listFiles('proj-legacy')
    expect(files.length).toBe(1)
    expect(files[0].project_id).toBe('proj-legacy')
    expect(files[0].analyzed).toBe(true)
    expect(files[0].document_id).toBe('doc-legacy-1')

    const cfg = await LocalWorkspace.getTranslationConfig()
    expect(cfg).not.toBeNull()
    const resolvedCfg = cfg as NonNullable<typeof cfg>
    expect(resolvedCfg.default_provider).toBe('deepl')
    expect(resolvedCfg.providers.find((provider) => provider.id === 'deepl')?.enabled).toBe(true)
    expect(resolvedCfg.providers.find((provider) => provider.id === 'gpt')?.enabled).toBe(true)
  })

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

  it('recovers visible history row when done-marker exists but current variant row is missing', async () => {
    const api = new HttpRuntimeApi()
    const selected = await LocalWorkspace.getSelectedProject()
    const projectId = String(selected.project_id || '')
    const mediaPath = '/client-media/done-recovery/01.Intro.mp3'
    const fileName = '01.Intro.mp3'

    await LocalWorkspace.cacheUploadedMedia(mediaPath, new Blob([new Uint8Array([1, 2, 3, 4])], { type: 'audio/mpeg' }))
    const file = await LocalWorkspace.registerMediaFile({
      projectId,
      name: fileName,
      mediaPath,
      sizeBytes: 4,
      durationSec: 1,
    })

    const contractDocId = await hashHex(`${fileName}|m2m100`)
    const variantDocId = await hashHex(`${fileName}|m2m100|backend_dmitry|bilingual_sequential`)
    const contract = {
      'Hello world.': {
        node_id: 's1',
        type: 'Sentence',
        content: 'Hello world.',
        tense: 'present',
        linguistic_notes: { elementary: '', intermediate: 'x', advanced: '' },
        part_of_speech: 'sentence',
        linguistic_elements: [],
        translations: { m2m100: { text: 'Привет, мир.' } },
      },
    }

    await LocalWorkspace.upsertAnalysis({
      documentId: contractDocId,
      projectId,
      mediaFileId: file.id,
      fileName,
      filePath: mediaPath,
      sizeBytes: 4,
      durationSeconds: 1,
      settings: 'Transl: m2m100 / Subs: bilingual_sequential / Voice: dmitry / Proc: incremental',
      contract,
      artifacts: LocalWorkspace.buildDocumentArtifacts(contractDocId, contract),
      contractCurrent: false,
    })

    await LocalWorkspace.cacheAnalysisArtifactBlob(
      variantDocId,
      'pipeline_settings.json',
      new Blob(
        [
          JSON.stringify({
            translationProvider: 'm2m100',
            voiceChoice: 'backend_dmitry',
            subtitlesMode: 'bilingual_sequential',
            sourceType: 'audio',
          }),
        ],
        { type: 'application/json' },
      ),
    )

    const payload = await api.submitMedia({
      mediaPath,
      durationSec: 1,
      sizeBytes: 4,
      projectId,
      mediaFileId: file.id,
      translationProvider: 'm2m100',
      subtitlesMode: 'bilingual_sequential',
      voiceChoice: 'backend_dmitry',
    })

    expect(payload.ui_feedback.message).toMatch(/already been analyzed/i)
    const history = await LocalWorkspace.listAnalysisHistory(projectId)
    const recovered = history.find((row) => row.document_id === variantDocId)
    expect(recovered).toBeTruthy()
    expect(recovered?.media_file_id).toBe(file.id)
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

  it('falls back to backend relay when DeepL direct browser fetch is blocked', async () => {
    const api = new HttpRuntimeApi()
    const fetchSpy = vi.spyOn(globalThis, 'fetch')
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ translations: { Hello: 'Привет' } }),
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
      'deepl',
      ['Hello'],
      { auth_key: 'test-auth-key:fx' },
      () => {},
    )

    expect(out.Hello).toBe('Привет')
    expect(fetchSpy).toHaveBeenCalledTimes(2)
    expect(String(fetchSpy.mock.calls[1][0])).toContain('/api/provider-translate')
  })

  it('returns cached translation config when workspace read fails', async () => {
    const api = new HttpRuntimeApi()
    window.localStorage.setItem(
      'ela_translation_config_cache_v1',
      JSON.stringify({
        default_provider: 'gpt',
        providers: [
          { id: 'm2m100', label: 'M2M100', kind: 'builtin', enabled: true, credential_fields: [], credentials: {} },
          { id: 'gpt', label: 'OpenAI GPT', kind: 'builtin', enabled: true, credential_fields: ['api_key'], credentials: { api_key: 'x' } },
          { id: 'original', label: 'Original only (no translation)', kind: 'builtin', enabled: true, credential_fields: [], credentials: {} },
        ],
      }),
    )
    vi.spyOn(LocalWorkspace, 'getTranslationConfig').mockRejectedValue(new Error('IDB read failed'))

    const cfg = await api.getTranslationConfig()
    expect(cfg.default_provider).toBe('gpt')
    expect(cfg.providers.find((provider) => provider.id === 'gpt')?.enabled).toBe(true)
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
