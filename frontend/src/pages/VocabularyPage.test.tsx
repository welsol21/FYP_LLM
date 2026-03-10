import { fireEvent, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { toExportRows, VocabularyPage, type VocabRow } from './VocabularyPage'
import { renderWithProviders } from '../test/testUtils'
import { MockRuntimeApi } from '../api/mockRuntimeApi'
import type { VisualizerNode, VisualizerPayload } from '../api/runtimeApi'

describe('VocabularyPage', () => {
  it('shows only analyzed files', async () => {
    renderWithProviders(<VocabularyPage />)
    expect(await screen.findByText('sample.mp4')).toBeInTheDocument()
    expect(screen.queryByText('draft.mp3')).not.toBeInTheDocument()
  })

  it('enables Visualizer button after selecting analyzed row', async () => {
    renderWithProviders(<VocabularyPage />)
    const visualizerBtn = await screen.findByRole('button', { name: 'Visualizer' })
    expect(visualizerBtn).toBeDisabled()

    fireEvent.click(await screen.findByTestId('vocab-row-doc-1'))
    expect(visualizerBtn).toBeEnabled()
  })

  it('shows items count from analysis history', async () => {
    const api = new MockRuntimeApi()
    vi.spyOn(api, 'listAnalysisHistory').mockResolvedValue([
      {
        analysis_id: 'doc-new',
        document_id: 'doc-1',
        project_id: 'proj-1',
        project_name: 'Demo Project',
        media_file_id: 'file-1',
        file_name: 'sample.mp4',
        file_path: '/uploads/sample.mp4',
        size_bytes: 104857600,
        duration_seconds: 600,
        settings: 'Transl: m2m100 / Subs: bilingual / Voice: male / Proc: incremental',
        items_count: 7,
        updated_at: '2026-03-08T12:25:33Z',
        created_at: '2026-03-08T12:24:32Z',
        contract_current: true,
      },
    ])

    renderWithProviders(<VocabularyPage />, api)
    expect(await screen.findByText('sample.mp4')).toBeInTheDocument()
    expect(await screen.findByText('7')).toBeInTheDocument()
  })

  it('shows all analysis history versions for the same file', async () => {
    const api = new MockRuntimeApi()
    vi.spyOn(api, 'listAnalysisHistory').mockResolvedValue([
      {
        analysis_id: 'doc-new',
        document_id: 'doc-1',
        project_id: 'proj-1',
        project_name: 'Demo Project',
        media_file_id: 'file-1',
        file_name: 'sample.mp4',
        file_path: '/uploads/sample.mp4',
        size_bytes: 104857600,
        duration_seconds: 600,
        settings: 'Transl: m2m100 / Subs: bilingual / Voice: male',
        updated_at: '2026-03-08T12:25:33Z',
        created_at: '2026-03-08T12:24:32Z',
        contract_current: true,
      },
      {
        analysis_id: 'doc-old',
        document_id: 'doc-old',
        project_id: 'proj-1',
        project_name: 'Demo Project',
        media_file_id: 'file-1',
        file_name: 'sample.mp4',
        file_path: '/uploads/sample.mp4',
        size_bytes: 104857600,
        duration_seconds: 600,
        settings: 'Transl: m2m100 / Subs: bilingual / Voice: male',
        updated_at: '2026-03-08T11:57:42Z',
        created_at: '2026-03-08T11:56:40Z',
        contract_current: true,
      },
    ])

    renderWithProviders(<VocabularyPage />, api)
    const rows = await screen.findAllByText('sample.mp4')
    expect(rows.length).toBe(2)
  })

  it('hides history rows without contract from vocabulary', async () => {
    const api = new MockRuntimeApi()
    vi.spyOn(api, 'listAnalysisHistory').mockResolvedValue([
      {
        analysis_id: 'doc-contract',
        document_id: 'doc-contract',
        project_id: 'proj-1',
        project_name: 'Demo Project',
        media_file_id: 'file-1',
        file_name: 'with-contract.mp3',
        file_path: '/uploads/with-contract.mp3',
        size_bytes: 104857600,
        duration_seconds: 600,
        settings: 'Transl: m2m100 / Subs: bilingual / Voice: male',
        updated_at: '2026-03-08T12:25:33Z',
        created_at: '2026-03-08T12:24:32Z',
        contract_current: true,
      },
      {
        analysis_id: 'doc-no-contract',
        document_id: 'doc-no-contract',
        project_id: 'proj-1',
        project_name: 'Demo Project',
        media_file_id: 'file-2',
        file_name: 'without-contract.mp3',
        file_path: '/uploads/without-contract.mp3',
        size_bytes: 104857600,
        duration_seconds: 600,
        settings: 'Transl: m2m100 / Subs: bilingual / Voice: male',
        updated_at: '2026-03-08T12:26:33Z',
        created_at: '2026-03-08T12:24:32Z',
        contract_current: false,
      },
    ])

    renderWithProviders(<VocabularyPage />, api)
    expect(await screen.findByText('with-contract.mp3')).toBeInTheDocument()
    expect(screen.queryByText('without-contract.mp3')).not.toBeInTheDocument()
  })

  it('exports selected provider translation rows', async () => {
    const payload: VisualizerPayload = {
      'Sentence one.': {
        node_id: 's1',
        type: 'Sentence',
        content: 'Sentence one.',
        tense: '',
        linguistic_notes: [],
        part_of_speech: 'sentence',
        translations: {
          backend_m2m100: { text: 'Sentence one.' },
        },
        linguistic_elements: [
          {
            node_id: 'w1',
            type: 'Word',
            content: 'She',
            tense: '',
            linguistic_notes: [],
            part_of_speech: 'pronoun',
            linguistic_elements: [],
            translations: {
              backend_m2m100: { text: 'Она' },
              gpt: { text: 'Она (GPT)' },
            },
          },
        ],
      },
    }
    const row: VocabRow = {
      id: 'row-1',
      project: 'Demo',
      file: 'sample.mp4',
      items: 1,
      created: 'Feb 18, 2026',
      settings: 'Transl: gpt / Subs: bilingual_sequential / Voice: male / Proc: incremental',
      documentId: 'doc-1',
      payload,
      translationProvider: 'gpt',
    }
    const rows = toExportRows(row)
    expect(rows[0].translation_provider).toBe('gpt')
    expect(rows[0].translation).toBe('Она (GPT)')
    expect(rows[0].translations_json).toContain('backend_m2m100')
    expect(rows[0].translations_json).toContain('gpt')
  })

  it('deletes selected analyses from vocabulary table', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderWithProviders(<VocabularyPage />)
    expect(await screen.findByText('sample.mp4')).toBeInTheDocument()

    fireEvent.click(await screen.findByTestId('vocab-row-doc-1'))
    fireEvent.click(screen.getByRole('button', { name: 'Delete Analyses' }))

    await waitFor(() => {
      expect(screen.queryByText('sample.mp4')).not.toBeInTheDocument()
    })
    confirmSpy.mockRestore()
  })
})
