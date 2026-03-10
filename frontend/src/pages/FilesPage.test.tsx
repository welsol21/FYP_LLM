import { fireEvent, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { FilesPage } from './FilesPage'
import { renderWithProviders } from '../test/testUtils'
import { MockRuntimeApi } from '../api/mockRuntimeApi'

const mockNavigate = vi.fn()

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  }
})

describe('FilesPage', () => {
  it('opens analyze on double-click for file row', async () => {
    renderWithProviders(<FilesPage />)
    const analyzedRow = await screen.findByLabelText('file-row-file-1')
    fireEvent.click(analyzedRow)
    fireEvent.click(analyzedRow)
    expect(mockNavigate).toHaveBeenCalledWith('/analyze', {
      state: {
        analyzeEntry: 'files',
        selectedMedia: {
          mediaFileId: 'file-1',
          documentId: 'doc-1',
          fileName: 'sample.mp4',
          mediaPath: '/uploads/sample.mp4',
          sizeBytes: 104857600,
          durationSec: 600,
        },
      },
    })
  })

  it('does not navigate on single tap/click', async () => {
    mockNavigate.mockClear()
    renderWithProviders(<FilesPage />)
    const draftRow = await screen.findByLabelText('file-row-file-2')
    fireEvent.click(draftRow)
    expect(mockNavigate).not.toHaveBeenCalled()
  })

  it('adds file in Files window by upload', async () => {
    renderWithProviders(<FilesPage />)
    const fileInput = (await screen.findByLabelText('Media File')) as HTMLInputElement
    const file = new File(['hello'], 'lesson.mp3', { type: 'audio/mpeg' })
    fireEvent.change(fileInput, { target: { files: [file] } })
    expect(await screen.findByText('lesson.mp3')).toBeInTheDocument()
  })

  it('shows analysis versions only after expanding a file row', async () => {
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
        settings: 'Transl: m2m100 / Subs: bilingual_simultaneous / Voice: female / Proc: force',
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
        settings: 'Transl: m2m100 / Subs: bilingual_sequential / Voice: male / Proc: incremental',
        updated_at: '2026-03-08T11:57:42Z',
        created_at: '2026-03-08T11:56:40Z',
        contract_current: true,
      },
    ])

    renderWithProviders(<FilesPage />, api)

    expect(await screen.findByLabelText('file-row-file-1')).toBeInTheDocument()
    expect(screen.queryByText('Subs: Bi-sim')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'toggle-versions-file-1' }))
    expect(await screen.findByText('Subs: Bi-sim')).toBeInTheDocument()
    expect(screen.getByText('Proc: Force')).toBeInTheDocument()
  })

  it('deletes file and its analysis versions', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderWithProviders(<FilesPage />)
    expect(await screen.findByLabelText('file-row-file-1')).toBeInTheDocument()
    expect(screen.getByText('sample.mp4')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'delete-file-file-1' }))

    await waitFor(() => {
      expect(screen.queryByLabelText('file-row-file-1')).not.toBeInTheDocument()
      expect(screen.queryByText('sample.mp4')).not.toBeInTheDocument()
    })
    confirmSpy.mockRestore()
  })
})
