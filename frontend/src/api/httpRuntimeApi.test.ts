import { beforeEach, describe, expect, it, vi } from 'vitest'
import { HttpRuntimeApi } from './httpRuntimeApi'
import { LocalWorkspace } from '../lib/localWorkspace'

describe('HttpRuntimeApi', () => {
  beforeEach(async () => {
    window.localStorage.clear()
    await LocalWorkspace.__resetForTests()
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
    expect(artifacts.some((row) => row.name === 'translated_audio_ru.mp3')).toBe(true)
    expect(artifacts.some((row) => row.name === 'translated_video_ru.mp4')).toBe(true)
    expect(artifacts.some((row) => row.name === 'media_contract.json')).toBe(true)
    expect(artifacts.some((row) => row.name === 'sentence_link.json')).toBe(true)
    expect(artifacts.some((row) => row.name === 'semantic_units_runtime.json')).toBe(true)
    expect(artifacts.some((row) => row.name === 'bilingual_objects_runtime.json')).toBe(true)
    expect(artifacts.some((row) => row.name === 'subtitles_target.srt')).toBe(true)
    expect(artifacts.some((row) => row.name === 'stage_manifest.json')).toBe(true)

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
})
