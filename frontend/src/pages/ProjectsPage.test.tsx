import { fireEvent, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ProjectsPage } from './ProjectsPage'
import { renderWithProviders } from '../test/testUtils'

const mockNavigate = vi.fn()

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  }
})

describe('ProjectsPage', () => {
  it('creates project from New Project button and shows it in table', async () => {
    renderWithProviders(<ProjectsPage />)
    fireEvent.click(await screen.findByRole('button', { name: 'New Project' }))
    await waitFor(() => {
      expect(screen.getByText('New Project 2')).toBeInTheDocument()
    })
  })

  it('opens files on project double tap/click', async () => {
    mockNavigate.mockClear()
    renderWithProviders(<ProjectsPage />)
    const row = await screen.findByLabelText('project-row-proj-1')
    fireEvent.click(row)
    fireEvent.click(row)
    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/files')
    })
  })
})
