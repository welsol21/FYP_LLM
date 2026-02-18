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
  it('creates project and shows it in table', async () => {
    renderWithProviders(<ProjectsPage />)
    fireEvent.change(screen.getByLabelText('new-project-name'), { target: { value: 'New Project' } })
    fireEvent.submit(screen.getByLabelText('project-create-form'))
    await waitFor(() => {
      expect(screen.getByText('New Project')).toBeInTheDocument()
    })
  })

  it('opens files on project double click', async () => {
    mockNavigate.mockClear()
    renderWithProviders(<ProjectsPage />)
    const row = await screen.findByLabelText('project-row-proj-1')
    fireEvent.doubleClick(row)
    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/files')
    })
  })
})
