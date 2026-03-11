import { beforeEach, describe, expect, it, vi } from 'vitest'
import { HttpRuntimeApi } from './httpRuntimeApi'
import { LocalWorkspace } from '../lib/localWorkspace'

describe('HttpRuntimeApi', () => {
  beforeEach(async () => {
    window.localStorage.clear()
    await LocalWorkspace.__resetForTests()
    await LocalWorkspace.createProject('Demo Project')
    vi.restoreAllMocks()
  })

  it('builds and persists analysis from client media blob using sentence-contract endpoint', async () => {
    const api = new HttpRuntimeApi()
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.includes('/api/sentence-contract')) {
        const body = JSON.parse(String(init?.body || '{}'))
        const sentenceText = String(body.sentenceText || '').trim() || 'She trusted him.'
        const payload = {
          sentence_text: sentenceText,
          sentence_hash: 'h-1',
          sentence_node: {
            node_id: 's-1',
            type: 'Sentence',
            content: sentenceText,
            tense: 'past',
            linguistic_notes: { elementary: '', intermediate: 'x', advanced: '' },
            part_of_speech: 'sentence',
            linguistic_elements: [],
            translations: { backend_m2m100: { text: 'Она доверяла ему.' } },
          },
        }
        return new Response(JSON.stringify(payload), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      }
      return new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } })
    })
    vi.stubGlobal('fetch', fetchMock as unknown as typeof fetch)

    const uploaded = await api.uploadMedia(new File(['She trusted him.'], '01.Intro.txt', { type: 'text/plain' }))
    const submit = await api.submitMedia({
      mediaPath: uploaded.mediaPath,
      durationSec: 10,
      sizeBytes: uploaded.sizeBytes,
    })

    const project = await api.getSelectedProject()
    const history = await api.listAnalysisHistory(project.project_id || undefined)
    const documentId = String(submit.result.document_id || '')
    const artifacts = await api.listDocumentArtifacts(documentId)
    expect(documentId).not.toBe('')
    expect(history.length).toBe(1)
    expect(history[0].document_id).toBe(documentId)
    expect(artifacts.some((row) => row.name === 'contract_sentences.json')).toBe(true)
    expect(fetchMock.mock.calls.some((call) => String(call[0]).includes('/api/sentence-contract'))).toBe(true)
    expect(fetchMock.mock.calls.some((call) => String(call[0]).includes('/api/submit-media'))).toBe(false)
  })

  it('keeps visualizer payload and artifacts fully local after submit', async () => {
    const api = new HttpRuntimeApi()
    let sentenceContractCalls = 0
    let visualizerCalls = 0
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.includes('/api/sentence-contract')) {
        sentenceContractCalls += 1
        const body = JSON.parse(String(init?.body || '{}'))
        const sentenceText = String(body.sentenceText || '').trim() || 'She trusted him.'
        const payload = {
          sentence_text: sentenceText,
          sentence_hash: 'h-2',
          sentence_node: {
            node_id: 's-2',
            type: 'Sentence',
            content: sentenceText,
            tense: 'past',
            linguistic_notes: { elementary: '', intermediate: 'x', advanced: '' },
            part_of_speech: 'sentence',
            linguistic_elements: [],
            translations: { backend_m2m100: { text: 'Она доверяла ему.' } },
          },
        }
        return new Response(JSON.stringify(payload), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      }
      if (url.includes('/api/visualizer-payload')) visualizerCalls += 1
      return new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } })
    })
    vi.stubGlobal('fetch', fetchMock as unknown as typeof fetch)

    const uploaded = await api.uploadMedia(new File(['She trusted him.'], '02.The Voice of Reason - I.txt', { type: 'text/plain' }))
    const submit = await api.submitMedia({
      mediaPath: uploaded.mediaPath,
      durationSec: 10,
      sizeBytes: uploaded.sizeBytes,
    })
    const documentId = String(submit.result.document_id || '')
    const artifacts = await api.listDocumentArtifacts(documentId)
    const payload = await api.getVisualizerPayload(documentId)
    expect(Object.keys(payload).length).toBeGreaterThan(0)
    expect(sentenceContractCalls).toBe(1)
    expect(visualizerCalls).toBe(0)
    expect(artifacts.some((row) => row.name === 'full_text.txt')).toBe(true)
    expect(artifacts.some((row) => row.name === 'contract_visualizer.json')).toBe(true)
    expect(artifacts.some((row) => row.name === 'contract_sentences.json')).toBe(true)
    expect(artifacts.some((row) => row.name === 'subtitles_en.srt')).toBe(true)
    expect(artifacts.some((row) => row.name === 'subtitles_bilingual.srt')).toBe(true)
    expect(artifacts.some((row) => row.name === 'translated_audio_ru.mp3')).toBe(false)
    expect(artifacts.some((row) => row.name === 'translated_video_ru.mp4')).toBe(false)
    expect(artifacts.some((row) => row.name === 'media_contract.json')).toBe(true)
    expect(artifacts.some((row) => row.name === 'sentence_link.json')).toBe(false)
    expect(artifacts.some((row) => row.name === 'semantic_units_runtime.json')).toBe(true)
    expect(artifacts.some((row) => row.name === 'bilingual_objects_runtime.json')).toBe(true)
    expect(artifacts.some((row) => row.name === 'subtitles_target.srt')).toBe(true)
    expect(artifacts.some((row) => row.name === 'stage_manifest.json')).toBe(false)

    // Persistence check across API instance recreation (SQLite snapshot restore).
    const apiReloaded = new HttpRuntimeApi()
    const project = await apiReloaded.getSelectedProject()
    const history = await apiReloaded.listAnalysisHistory(project.project_id || undefined)
    expect(history.some((row) => row.document_id === documentId)).toBe(true)
  })

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
        translations: { backend_m2m100: { text: 'Она пришла домой.' } },
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

  it('saves no-contract analysis with user-friendly service message and downloadable artifacts', async () => {
    const api = new HttpRuntimeApi()
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/api/sentence-contract')) {
        return new Response(JSON.stringify({ error: 'Not found' }), {
          status: 404,
          headers: { 'Content-Type': 'application/json' },
        })
      }
      return new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } })
    })
    vi.stubGlobal('fetch', fetchMock as unknown as typeof fetch)

    const uploaded = await api.uploadMedia(new File(['One sentence only.'], 'fallback.txt', { type: 'text/plain' }))
    const project = await api.getSelectedProject()
    const file = await api.registerMediaFile({
      projectId: String(project.project_id || ''),
      name: uploaded.fileName,
      mediaPath: uploaded.mediaPath,
      sizeBytes: uploaded.sizeBytes,
      durationSec: 1,
    })

    const submit = await api.submitMedia({
      mediaPath: uploaded.mediaPath,
      durationSec: 1,
      sizeBytes: uploaded.sizeBytes,
      mediaFileId: file.id,
      translationProvider: 'm2m100',
      subtitlesMode: 'bilingual_sequential',
    })

    expect(submit.result.status).toBe('completed_local_no_contract')
    expect((submit.result.stage_logs || []).join('\n')).toContain('Project service is unavailable')
    expect((submit.result.stage_logs || []).join('\n')).not.toContain('HTTP 404')

    const history = await api.listAnalysisHistory(project.project_id || undefined)
    expect(history.length).toBeGreaterThan(0)
    const docId = String(history[0]?.document_id || '')
    const artifacts = await api.listDocumentArtifacts(docId)
    expect(artifacts.length).toBeGreaterThan(0)
    expect(artifacts.every((a) => typeof a.download_url === 'string' && a.download_url.length > 0)).toBe(true)
    expect(artifacts.some((a) => a.name === 'subtitles_bilingual.srt')).toBe(true)
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
})
