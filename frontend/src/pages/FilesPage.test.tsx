import { fireEvent, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { FilesPage } from './FilesPage'
import { renderWithProviders } from '../test/testUtils'

const mockNavigate = vi.fn()

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  }
})

describe('FilesPage', () => {
  it('opens visualizer on double-click for analyzed file', async () => {
    renderWithProviders(<FilesPage />)
    const analyzedRow = await screen.findByLabelText('file-row-file-1')
    fireEvent.doubleClick(analyzedRow)
    expect(mockNavigate).toHaveBeenCalledWith('/visualizer', { state: { documentId: 'doc-1' } })
  })

  it('does not navigate for non-analyzed file', async () => {
    mockNavigate.mockClear()
    renderWithProviders(<FilesPage />)
    const draftRow = await screen.findByLabelText('file-row-file-2')
    fireEvent.doubleClick(draftRow)
    expect(mockNavigate).not.toHaveBeenCalled()
  })
})

