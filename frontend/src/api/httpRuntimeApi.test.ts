import { beforeEach, describe, expect, it, vi } from 'vitest'
import { HttpRuntimeApi } from './httpRuntimeApi'

describe('HttpRuntimeApi', () => {
  beforeEach(() => {
    window.localStorage.clear()
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
      if (url.includes('/api/document-artifacts')) {
        return new Response(
          JSON.stringify([
            { name: 'full_text.txt', size_bytes: 123, download_url: '/api/document-artifact-download?document_id=doc-1&name=full_text.txt' },
            { name: 'subtitles_en.srt', size_bytes: 456, download_url: '/api/document-artifact-download?document_id=doc-1&name=subtitles_en.srt' },
            { name: 'contract_sentences.json', size_bytes: 789, download_url: '/api/document-artifact-download?document_id=doc-1&name=contract_sentences.json' },
          ]),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        )
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
    expect(artifacts.some((row) => row.name === 'subtitles_en.srt')).toBe(true)
  })
})
