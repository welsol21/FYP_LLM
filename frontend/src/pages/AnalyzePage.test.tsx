import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { AnalyzePage } from './AnalyzePage'
import { ApiContext } from '../api/apiContext'
import { MockRuntimeApi } from '../api/mockRuntimeApi'

describe('AnalyzePage', () => {
  it('shows compact analyze panel with selected file and submit feedback', async () => {
    const api = new MockRuntimeApi()
    render(
      <ApiContext.Provider value={api}>
        <MemoryRouter
          initialEntries={[
            {
              pathname: '/analyze',
              state: {
                analyzeEntry: 'files',
                selectedMedia: {
                  mediaFileId: 'file-1',
                  fileName: 'sample.mp4',
                  mediaPath: '/uploads/sample.mp4',
                  sizeBytes: 104857600,
                  durationSec: 600,
                },
              },
            },
          ]}
        >
          <AnalyzePage />
        </MemoryRouter>
      </ApiContext.Provider>,
    )
    await waitFor(() => {
      expect(screen.getByText('Demo Project')).toBeInTheDocument()
      expect(screen.getByText('sample.mp4')).toBeInTheDocument()
    })
    expect(screen.queryByLabelText('analyze-direct-select')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Start pipeline' }))

    await waitFor(() => {
      expect(screen.getByText(/Local processing completed/i)).toBeInTheDocument()
    })
  })

  it('allows selecting project and file when opened directly', async () => {
    const api = new MockRuntimeApi()
    render(
      <ApiContext.Provider value={api}>
        <MemoryRouter initialEntries={[{ pathname: '/analyze' }]}>
          <AnalyzePage />
        </MemoryRouter>
      </ApiContext.Provider>,
    )

    const directSelect = await screen.findByLabelText('analyze-direct-select')
    expect(directSelect).toBeInTheDocument()
    const useBtn = within(directSelect).getByRole('button', { name: 'Use selected file' }) as HTMLButtonElement
    expect(useBtn.disabled).toBe(true)

    fireEvent.click(within(directSelect).getByRole('button', { name: 'Demo Project' }))
    await waitFor(() => {
      expect(within(directSelect).getByRole('button', { name: 'sample.mp4' })).toBeInTheDocument()
    })
    fireEvent.click(within(directSelect).getByRole('button', { name: 'sample.mp4' }))

    await waitFor(() => expect(useBtn.disabled).toBe(false))
    fireEvent.click(useBtn)

    await waitFor(() => {
      expect(screen.getAllByText('sample.mp4').length).toBeGreaterThan(0)
    })
  })

  it('shows empty history until current file is selected', async () => {
    const api = new MockRuntimeApi()
    render(
      <ApiContext.Provider value={api}>
        <MemoryRouter initialEntries={[{ pathname: '/analyze' }]}>
          <AnalyzePage />
        </MemoryRouter>
      </ApiContext.Provider>,
    )

    const historyCard = await screen.findByLabelText('analyze-history')
    const directSelect = await screen.findByLabelText('analyze-direct-select')
    await waitFor(() => {
      expect(within(historyCard).getByText('No analyzed files yet.')).toBeInTheDocument()
    })

    fireEvent.click(within(directSelect).getByRole('button', { name: 'Demo Project' }))
    await waitFor(() => expect(within(directSelect).getByRole('button', { name: 'sample.mp4' })).toBeInTheDocument())
    fireEvent.click(within(directSelect).getByRole('button', { name: 'sample.mp4' }))
    const useBtn = within(directSelect).getByRole('button', { name: 'Use selected file' }) as HTMLButtonElement
    await waitFor(() => expect(useBtn.disabled).toBe(false))
    fireEvent.click(useBtn)

    await waitFor(() => {
      expect(within(historyCard).getByText('sample.mp4')).toBeInTheDocument()
      expect(within(historyCard).getByRole('link', { name: /Download contract_sentences.json/i })).toBeInTheDocument()
    })
  })

  it('deletes analysis artifacts from history entry', async () => {
    const api = new MockRuntimeApi()
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
    render(
      <ApiContext.Provider value={api}>
        <MemoryRouter initialEntries={[{ pathname: '/analyze' }]}>
          <AnalyzePage />
        </MemoryRouter>
      </ApiContext.Provider>,
    )

    const directSelect = await screen.findByLabelText('analyze-direct-select')
    fireEvent.click(within(directSelect).getByRole('button', { name: 'Demo Project' }))
    await waitFor(() => expect(within(directSelect).getByRole('button', { name: 'sample.mp4' })).toBeInTheDocument())
    fireEvent.click(within(directSelect).getByRole('button', { name: 'sample.mp4' }))
    const useBtn = within(directSelect).getByRole('button', { name: 'Use selected file' }) as HTMLButtonElement
    await waitFor(() => expect(useBtn.disabled).toBe(false))
    fireEvent.click(useBtn)

    const historyCard = await screen.findByLabelText('analyze-history')
    const deleteBtn = await within(historyCard).findByRole('button', { name: 'history-delete-doc-1' })
    fireEvent.click(deleteBtn)

    await waitFor(() => {
      expect(within(historyCard).queryByText('sample.mp4')).not.toBeInTheDocument()
    })
    confirmSpy.mockRestore()
  })

  it('does not show visualizer action for history versions without contract', async () => {
    const api = new MockRuntimeApi()
    vi.spyOn(api, 'listAnalysisHistory').mockResolvedValue([
      {
        analysis_id: 'doc-no-contract',
        document_id: 'doc-no-contract',
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
        contract_current: false,
      },
    ])
    vi.spyOn(api, 'listDocumentArtifacts').mockResolvedValue([
      { name: 'subtitles_en.srt', size_bytes: 123, download_url: 'data:text/plain,ok' },
    ])

    render(
      <ApiContext.Provider value={api}>
        <MemoryRouter
          initialEntries={[
            {
              pathname: '/analyze',
              state: {
                analyzeEntry: 'files',
                selectedMedia: {
                  mediaFileId: 'file-1',
                  fileName: 'sample.mp4',
                  mediaPath: '/uploads/sample.mp4',
                  sizeBytes: 104857600,
                  durationSec: 600,
                },
              },
            },
          ]}
        >
          <AnalyzePage />
        </MemoryRouter>
      </ApiContext.Provider>,
    )

    const historyCard = await screen.findByLabelText('analyze-history')
    await waitFor(() => {
      expect(within(historyCard).queryByRole('button', { name: /history-open-sample.mp4/i })).not.toBeInTheDocument()
      expect(within(historyCard).getByText(/Visualizer unavailable: backend contract was not received./i)).toBeInTheDocument()
    })
  })

})
