import { fireEvent, screen, waitFor } from '@testing-library/react'
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { ApiContext } from '../api/apiContext'
import type { RuntimeApi, VisualizerPayload } from '../api/runtimeApi'
import { VisualizerPage } from './VisualizerPage'
import { renderWithProviders } from '../test/testUtils'

describe('VisualizerPage', () => {
  it('renders visualizer tree payload', async () => {
    renderWithProviders(<VisualizerPage />)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'select-node-n1' })).toBeInTheDocument()
    })
    expect(screen.getByText('She')).toBeInTheDocument()
    expect(screen.getByText('should have trusted her instincts')).toBeInTheDocument()
    expect(screen.getByText('before making the decision')).toBeInTheDocument()
    expect(screen.getAllByText('B2').length).toBeGreaterThan(0)
    expect(screen.getAllByText(/CEFR:/).length).toBeGreaterThan(0)
  })

  it('applies node edit from label selection and updates rendered content', async () => {
    renderWithProviders(<VisualizerPage />)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'toggle-children-n1' })).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: 'toggle-children-n1' }))
    fireEvent.click(screen.getByRole('button', { name: 'select-node-n4' }))
    fireEvent.change(screen.getByLabelText(/New Content/), { target: { value: 'trusted them' } })
    fireEvent.click(screen.getByRole('button', { name: 'Apply Edit' }))

    await waitFor(() => {
      expect(screen.getByText('Edit applied.')).toBeInTheDocument()
    })
  })

  it('loads document-scoped payload and navigates within selected document', async () => {
    const docPayload: VisualizerPayload = {
      'Sentence one.': {
        node_id: 's1',
        type: 'Sentence',
        content: 'Sentence one.',
        tense: 'null',
        linguistic_notes: [],
        part_of_speech: 'sentence',
        linguistic_elements: [],
      },
      'Sentence two.': {
        node_id: 's2',
        type: 'Sentence',
        content: 'Sentence two.',
        tense: 'null',
        linguistic_notes: [],
        part_of_speech: 'sentence',
        linguistic_elements: [],
      },
    }
    const getVisualizerPayload = vi.fn(async (documentId?: string) => {
      if (documentId === 'doc-42') return docPayload
      return {}
    })
    const api: RuntimeApi = {
      getUiState: async () => ({
        runtime_mode: 'online',
        deployment_mode: 'local',
        badges: {},
        features: {
          phonetic: { enabled: true, reason_if_disabled: '' },
          db_persistence: { enabled: true, reason_if_disabled: '' },
        },
      }),
      listProjects: async () => [{ id: 'proj-1', name: 'Demo', created_at: '2026-02-18T00:00:00Z', updated_at: '2026-02-18T00:00:00Z' }],
      createProject: async (name: string) => ({
        id: 'proj-2',
        name,
        created_at: '2026-02-18T00:00:00Z',
        updated_at: '2026-02-18T00:00:00Z',
      }),
      getSelectedProject: async () => ({ project_id: 'proj-1', project_name: 'Demo' }),
      setSelectedProject: async () => ({ project_id: 'proj-1', project_name: 'Demo' }),
      registerMediaFile: async () => ({
        id: 'file-1',
        project_id: 'proj-1',
        name: 'demo.mp3',
        path: '/tmp/demo.mp3',
      }),
      submitMedia: async () => ({
        result: { route: 'local', message: '' },
        ui_feedback: { severity: 'info', title: '', message: '' },
      }),
      listFiles: async () => [],
      uploadMedia: async () => ({ fileName: 'uploaded.txt', mediaPath: '/tmp/uploaded.txt', sizeBytes: 12 }),
      getVisualizerPayload,
      applyEdit: async () => ({ status: 'ok', message: 'Edit applied.' }),
      getTranslationConfig: async () => ({
        default_provider: 'm2m100',
        providers: [{ id: 'm2m100', label: 'Our Translator (M2M100)', kind: 'builtin', enabled: true, credential_fields: [], credentials: {} }],
      }),
      saveTranslationConfig: async (config) => config,
    }

    render(
      <ApiContext.Provider value={api}>
        <MemoryRouter initialEntries={[{ pathname: '/visualizer', state: { documentId: 'doc-42' } }]}>
          <VisualizerPage />
        </MemoryRouter>
      </ApiContext.Provider>,
    )

    await waitFor(() => {
      expect(screen.getByText('Sentence one.')).toBeInTheDocument()
    })
    expect(getVisualizerPayload).toHaveBeenCalledWith('doc-42')
    expect(screen.getByText('1 / 2')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    await waitFor(() => {
      expect(screen.getByText('Sentence two.')).toBeInTheDocument()
    })
    expect(screen.getByText('2 / 2')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Prev' }))
    await waitFor(() => {
      expect(screen.getByText('Sentence one.')).toBeInTheDocument()
    })
    expect(screen.getByText('1 / 2')).toBeInTheDocument()
  })
})
