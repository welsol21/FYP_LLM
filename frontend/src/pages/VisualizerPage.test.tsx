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

  it('auto-selects root sentence node and pre-fills content editor', async () => {
    renderWithProviders(<VisualizerPage />)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'select-node-n1' })).toBeInTheDocument()
    })

    await waitFor(() => {
      expect(screen.getByText(/Selected Node:\s*sentence/i)).toBeInTheDocument()
      const editorInput = screen.getByLabelText('New Content') as HTMLInputElement | HTMLTextAreaElement
      expect(editorInput.value).toBe('She should have trusted her instincts before making the decision.')
    })
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

  it('resets quick editor to content on node select and exposes all note levels', async () => {
    renderWithProviders(<VisualizerPage />)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'toggle-children-n1' })).toBeInTheDocument()
    })

    expect(screen.getByRole('button', { name: 'Linguistic Notes (Elementary)' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Linguistic Notes (Intermediate)' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Linguistic Notes (Advanced)' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'CEFR' }))
    fireEvent.click(screen.getByRole('button', { name: 'toggle-children-n1' }))
    fireEvent.click(screen.getByRole('button', { name: 'select-node-n4' }))

    const editorInput = screen.getByLabelText('New Content') as HTMLInputElement
    expect(editorInput.value).toBe('should have trusted her instincts')
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
        translations: {
          backend_m2m100: { text: 'Sentence one.' },
        },
        linguistic_elements: [],
      },
      'Sentence two.': {
        node_id: 's2',
        type: 'Sentence',
        content: 'Sentence two.',
        tense: 'null',
        linguistic_notes: [],
        part_of_speech: 'sentence',
        translations: {
          backend_m2m100: { text: 'Sentence two.' },
        },
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
      deleteFile: async () => ({ status: 'ok', message: 'deleted' }),
      listAnalysisHistory: async () => [],
      deleteAnalysis: async () => ({ status: 'ok', message: 'deleted' }),
      listDocumentArtifacts: async () => [],
      uploadMedia: async () => ({ fileName: 'uploaded.txt', mediaPath: '/tmp/uploaded.txt', sizeBytes: 12 }),
      getVisualizerPayload,
      analyzeText: async () => ({ raw_text: '', sentences: [], razbor: [], contract: {} }),
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
      expect(screen.getAllByText('Sentence one.').length).toBeGreaterThan(0)
    })
    expect(getVisualizerPayload).toHaveBeenCalledWith('doc-42')
    expect(screen.getByText('1 / 2')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(screen.getByRole('button', { name: 'toggle-quick-edit' })).toBeInTheDocument()
    expect(screen.queryByText(/Selected Node:/i)).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    await waitFor(() => {
      expect(screen.getAllByText('Sentence two.').length).toBeGreaterThan(0)
    })
    expect(screen.getByText('2 / 2')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'toggle-quick-edit' })).toBeInTheDocument()
    expect(screen.queryByText(/Selected Node:/i)).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Prev' }))
    await waitFor(() => {
      expect(screen.getAllByText('Sentence one.').length).toBeGreaterThan(0)
    })
    expect(screen.getByText('1 / 2')).toBeInTheDocument()
  })

  it('keeps quick edit and translate forms open across sentence navigation', async () => {
    const docPayload: VisualizerPayload = {
      'Sentence one.': {
        node_id: 's1',
        type: 'Sentence',
        content: 'Sentence one.',
        tense: 'null',
        linguistic_notes: [],
        part_of_speech: 'sentence',
        translations: {
          backend_m2m100: { text: 'Sentence one.' },
        },
        linguistic_elements: [],
      },
      'Sentence two.': {
        node_id: 's2',
        type: 'Sentence',
        content: 'Sentence two.',
        tense: 'null',
        linguistic_notes: [],
        part_of_speech: 'sentence',
        translations: {
          backend_m2m100: { text: 'Sentence two.' },
        },
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
      deleteFile: async () => ({ status: 'ok', message: 'deleted' }),
      listAnalysisHistory: async () => [],
      deleteAnalysis: async () => ({ status: 'ok', message: 'deleted' }),
      listDocumentArtifacts: async () => [],
      uploadMedia: async () => ({ fileName: 'uploaded.txt', mediaPath: '/tmp/uploaded.txt', sizeBytes: 12 }),
      getVisualizerPayload,
      analyzeText: async () => ({ raw_text: '', sentences: [], razbor: [], contract: {} }),
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
      expect(screen.getAllByText('Sentence one.').length).toBeGreaterThan(0)
    })
    expect(screen.getByText(/Selected Node:/i)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    await waitFor(() => {
      expect(screen.getAllByText('Sentence two.').length).toBeGreaterThan(0)
    })
    expect(screen.getByText(/Selected Node:/i)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'toggle-translate-controls' }))
    expect(screen.getByText('Translation provider')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Prev' }))
    await waitFor(() => {
      expect(screen.getAllByText('Sentence one.').length).toBeGreaterThan(0)
    })
    expect(screen.getByText('Translation provider')).toBeInTheDocument()
  })

  it('switches translation provider with backend fallback', async () => {
    const docPayload: VisualizerPayload = {
      'Sentence one.': {
        node_id: 's1',
        type: 'Sentence',
        content: 'Sentence one.',
        tense: 'null',
        linguistic_notes: [],
        part_of_speech: 'sentence',
        active_translation_provider: 'gpt',
        translations: {
          backend_m2m100: { text: 'Backend translation', source_lang: 'en', target_lang: 'ru' },
          gpt: { text: 'GPT translation', source_lang: 'en', target_lang: 'ru' },
        },
        linguistic_elements: [],
      },
    }
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
      listProjects: async () => [],
      createProject: async (name: string) => ({
        id: 'proj-2',
        name,
        created_at: '2026-02-18T00:00:00Z',
        updated_at: '2026-02-18T00:00:00Z',
      }),
      getSelectedProject: async () => ({ project_id: null }),
      setSelectedProject: async () => ({ project_id: null }),
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
      deleteFile: async () => ({ status: 'ok', message: 'deleted' }),
      listAnalysisHistory: async () => [],
      deleteAnalysis: async () => ({ status: 'ok', message: 'deleted' }),
      listDocumentArtifacts: async () => [],
      uploadMedia: async () => ({ fileName: 'uploaded.txt', mediaPath: '/tmp/uploaded.txt', sizeBytes: 12 }),
      getVisualizerPayload: async () => docPayload,
      analyzeText: async () => ({ raw_text: '', sentences: [], razbor: [], contract: {} }),
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
      expect(screen.getByText('GPT translation')).toBeInTheDocument()
    })
    fireEvent.click(screen.getByRole('button', { name: 'toggle-translate-controls' }))
    fireEvent.click(screen.getByRole('button', { name: 'backend_m2m100' }))
    await waitFor(() => {
      expect(screen.getByText('Backend translation')).toBeInTheDocument()
    })
    expect(screen.getByRole('button', { name: 'More translations (1)' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'More translations (1)' }))
    expect(screen.getByText('client_gpt:')).toBeInTheDocument()
    expect(screen.getByText('GPT translation')).toBeInTheDocument()
  })

  it('builds a single Prev/Next stream for multiple selected documents', async () => {
    const payloadDocA: VisualizerPayload = {
      'Doc A sentence.': {
        node_id: 'a1',
        type: 'Sentence',
        content: 'Doc A sentence.',
        tense: 'null',
        linguistic_notes: [],
        part_of_speech: 'sentence',
        translations: { backend_m2m100: { text: 'A' } },
        linguistic_elements: [],
      },
    }
    const payloadDocB: VisualizerPayload = {
      'Doc B sentence.': {
        node_id: 'b1',
        type: 'Sentence',
        content: 'Doc B sentence.',
        tense: 'null',
        linguistic_notes: [],
        part_of_speech: 'sentence',
        translations: { backend_m2m100: { text: 'B' } },
        linguistic_elements: [],
      },
    }
    const getVisualizerPayload = vi.fn(async (documentId?: string) => {
      if (documentId === 'doc-a') return payloadDocA
      if (documentId === 'doc-b') return payloadDocB
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
      listProjects: async () => [],
      createProject: async (name: string) => ({ id: 'proj', name, created_at: '', updated_at: '' }),
      getSelectedProject: async () => ({ project_id: null }),
      setSelectedProject: async () => ({ project_id: null }),
      registerMediaFile: async () => ({ id: 'f', project_id: 'p', name: 'x', path: '/tmp/x' }),
      submitMedia: async () => ({ result: { route: 'local', message: '' }, ui_feedback: { severity: 'info', title: '', message: '' } }),
      listFiles: async () => [],
      deleteFile: async () => ({ status: 'ok', message: 'deleted' }),
      listAnalysisHistory: async () => [],
      deleteAnalysis: async () => ({ status: 'ok', message: 'deleted' }),
      listDocumentArtifacts: async () => [],
      uploadMedia: async () => ({ fileName: 'u.txt', mediaPath: '/tmp/u.txt', sizeBytes: 10 }),
      getVisualizerPayload,
      analyzeText: async () => ({ raw_text: '', sentences: [], razbor: [], contract: {} }),
      applyEdit: async () => ({ status: 'ok', message: 'Edit applied.' }),
      getTranslationConfig: async () => ({
        default_provider: 'm2m100',
        providers: [{ id: 'm2m100', label: 'Our Translator (M2M100)', kind: 'builtin', enabled: true, credential_fields: [], credentials: {} }],
      }),
      saveTranslationConfig: async (config) => config,
    }

    render(
      <ApiContext.Provider value={api}>
        <MemoryRouter
          initialEntries={[
            {
              pathname: '/visualizer',
              state: {
                documentIds: ['doc-a', 'doc-b'],
                documentMeta: {
                  'doc-a': { project: 'Project A', file: 'a.txt' },
                  'doc-b': { project: 'Project B', file: 'b.txt' },
                },
              },
            },
          ]}
        >
          <VisualizerPage />
        </MemoryRouter>
      </ApiContext.Provider>,
    )

    await waitFor(() => {
      expect(screen.getAllByText('Doc A sentence.').length).toBeGreaterThan(0)
    })
    expect(getVisualizerPayload).toHaveBeenCalledWith('doc-a')
    expect(getVisualizerPayload).toHaveBeenCalledWith('doc-b')
    expect(screen.getByText('1 / 2')).toBeInTheDocument()
    expect(screen.getByText(/Project:/)).toBeInTheDocument()
    expect(screen.getByText(/Project A/)).toBeInTheDocument()
    expect(screen.getByText(/File:/)).toBeInTheDocument()
    expect(screen.getByText(/a\.txt/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    await waitFor(() => {
      expect(screen.getAllByText('Doc B sentence.').length).toBeGreaterThan(0)
    })
    expect(screen.getByText('2 / 2')).toBeInTheDocument()
    expect(screen.getByText(/Project B/)).toBeInTheDocument()
    expect(screen.getByText(/b\.txt/)).toBeInTheDocument()
  })
})
