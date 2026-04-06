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
      expect(within(historyCard).getByRole('link', { name: /contract_sentences\.json/i })).toBeInTheDocument()
    })
  })

  it('keeps configured translators after transient translation-config load failure', async () => {
    const api = new MockRuntimeApi()
    await api.saveTranslationConfig({
      default_provider: 'gpt',
      providers: [
        { id: 'm2m100', label: 'M2M100', kind: 'builtin', enabled: true, credential_fields: [], credentials: {} },
        { id: 'gpt', label: 'OpenAI GPT', kind: 'builtin', enabled: true, credential_fields: ['api_key'], credentials: { api_key: 'x' } },
        { id: 'deepl', label: 'DeepL', kind: 'builtin', enabled: false, credential_fields: ['auth_key'], credentials: { auth_key: '' } },
        { id: 'lara', label: 'Lara', kind: 'builtin', enabled: false, credential_fields: ['api_id', 'api_secret'], credentials: { api_id: '', api_secret: '' } },
        { id: 'original', label: 'Original only (no translation)', kind: 'builtin', enabled: true, credential_fields: [], credentials: {} },
      ],
    })
    const originalGetConfig = api.getTranslationConfig.bind(api)
    vi
      .spyOn(api, 'getTranslationConfig')
      .mockRejectedValueOnce(new Error('IDB temporary failure'))
      .mockImplementation(originalGetConfig)

    render(
      <ApiContext.Provider value={api}>
        <MemoryRouter initialEntries={[{ pathname: '/analyze' }]}>
          <AnalyzePage />
        </MemoryRouter>
      </ApiContext.Provider>,
    )

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'OpenAI GPT' })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'M2M100' })).toBeInTheDocument()
    })
  })

  it('shows history for re-registered file when media_file_id changed but path/name match', async () => {
    const api = new MockRuntimeApi()
    const originalList = api.listAnalysisHistory.bind(api)
    vi.spyOn(api, 'listAnalysisHistory').mockImplementation(async (projectId?: string) => {
      const rows = await originalList(projectId)
      return rows.map((row, idx) => (idx === 0 ? { ...row, media_file_id: 'file-old-id' } : row))
    })

    render(
      <ApiContext.Provider value={api}>
        <MemoryRouter initialEntries={[{ pathname: '/analyze' }]}>
          <AnalyzePage />
        </MemoryRouter>
      </ApiContext.Provider>,
    )

    const historyCard = await screen.findByLabelText('analyze-history')
    const directSelect = await screen.findByLabelText('analyze-direct-select')
    fireEvent.click(within(directSelect).getByRole('button', { name: 'Demo Project' }))
    await waitFor(() => expect(within(directSelect).getByRole('button', { name: 'sample.mp4' })).toBeInTheDocument())
    fireEvent.click(within(directSelect).getByRole('button', { name: 'sample.mp4' }))
    const useBtn = within(directSelect).getByRole('button', { name: 'Use selected file' }) as HTMLButtonElement
    await waitFor(() => expect(useBtn.disabled).toBe(false))
    fireEvent.click(useBtn)

    await waitFor(() => {
      expect(within(historyCard).getByText('sample.mp4')).toBeInTheDocument()
      expect(within(historyCard).getByRole('link', { name: /contract_sentences\.json/i })).toBeInTheDocument()
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

})
