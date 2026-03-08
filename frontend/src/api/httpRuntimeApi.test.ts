import { beforeEach, describe, expect, it, vi } from 'vitest'
import { HttpRuntimeApi } from './httpRuntimeApi'
import { LocalWorkspace } from '../lib/localWorkspace'

describe('HttpRuntimeApi', () => {
  beforeEach(async () => {
    window.localStorage.clear()
    await LocalWorkspace.__resetForTests()
    vi.restoreAllMocks()
  })

  it('persists analysis history when completed_local payload appears after short delay', async () => {
    const api = new HttpRuntimeApi()
    let visualizerCalls = 0
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/api/submit-media')) {
        return new Response(
          JSON.stringify({
            result: { route: 'local', status: 'accepted_local', message: 'accepted', job_id: 'job-1' },
            ui_feedback: { severity: 'info', title: 'ok', message: 'accepted' },
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        )
      }
      if (url.includes('/api/backend-job-status')) {
        return new Response(
          JSON.stringify({
            job_id: 'job-1',
            status: 'completed_local',
            message: 'done',
            stage_progress: [100, 100, 100, 100, 100],
            document_id: 'doc-1',
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        )
      }
      if (url.includes('/api/visualizer-payload')) {
        visualizerCalls += 1
        const payload =
          visualizerCalls < 3
            ? {}
            : {
                'She trusted him.': {
                  node_id: 's-1',
                  type: 'Sentence',
                  content: 'She trusted him.',
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

    await api.submitMedia({
      mediaPath: '/uploads/01.Intro.mp3',
      durationSec: 10,
      sizeBytes: 1024,
    })
    await api.getBackendJobStatus('job-1')

    const project = await api.getSelectedProject()
    const history = await api.listAnalysisHistory(project.project_id || undefined)
    const artifacts = await api.listDocumentArtifacts('doc-1')
    expect(visualizerCalls).toBeGreaterThanOrEqual(3)
    expect(history.length).toBe(1)
    expect(history[0].document_id).toBe('doc-1')
    expect(artifacts.some((row) => row.name === 'contract_sentences.json')).toBe(true)
  })

  it('generates downloadable contract artifacts locally without backend artifacts endpoint', async () => {
    const api = new HttpRuntimeApi()
    let visualizerCalls = 0
    let artifactCalls = 0
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/api/submit-media')) {
        return new Response(
          JSON.stringify({
            result: { route: 'local', status: 'accepted_local', message: 'accepted', job_id: 'job-2' },
            ui_feedback: { severity: 'info', title: 'ok', message: 'accepted' },
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        )
      }
      if (url.includes('/api/backend-job-status')) {
        return new Response(
          JSON.stringify({
            job_id: 'job-2',
            status: 'completed_local',
            message: 'done',
            stage_progress: [100, 100, 100, 100, 100],
            document_id: 'doc-2',
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        )
      }
      if (url.includes('/api/visualizer-payload')) {
        visualizerCalls += 1
        const payload =
          visualizerCalls < 2
            ? {}
            : {
                'She trusted him.': {
                  node_id: 's-2',
                  type: 'Sentence',
                  content: 'She trusted him.',
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
      if (url.includes('/api/document-artifacts')) artifactCalls += 1
      return new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } })
    })
    vi.stubGlobal('fetch', fetchMock as unknown as typeof fetch)

    await api.submitMedia({
      mediaPath: '/uploads/02.The Voice of Reason - I.mp3',
      durationSec: 10,
      sizeBytes: 1024,
    })
    await api.getBackendJobStatus('job-2')
    const artifacts = await api.listDocumentArtifacts('doc-2')
    expect(artifactCalls).toBe(0)
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
    expect(history.some((row) => row.document_id === 'doc-2')).toBe(true)
  })
})
