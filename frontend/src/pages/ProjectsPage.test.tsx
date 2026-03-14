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
    const promptSpy = vi.spyOn(window, 'prompt').mockReturnValue('Custom Project')
    renderWithProviders(<ProjectsPage />)
    fireEvent.click(await screen.findByRole('button', { name: 'New Project' }))
    await waitFor(() => {
      expect(screen.getAllByText('Custom Project').length).toBeGreaterThan(0)
    })
    promptSpy.mockRestore()
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

  it('deletes project with cascade action button', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderWithProviders(<ProjectsPage />)
    const deleteBtn = await screen.findByRole('button', { name: 'delete-project-proj-1' })
    fireEvent.click(deleteBtn)
    await waitFor(() => {
      expect(screen.queryByLabelText('project-row-proj-1')).not.toBeInTheDocument()
    })
    confirmSpy.mockRestore()
  })

  it('rejects duplicate project name', async () => {
    const promptSpy = vi.spyOn(window, 'prompt')
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => undefined)
    renderWithProviders(<ProjectsPage />)

    promptSpy.mockReturnValueOnce('Unique Project')
    fireEvent.click(await screen.findByRole('button', { name: 'New Project' }))
    await waitFor(() => {
      expect(screen.getAllByText('Unique Project').length).toBeGreaterThan(0)
    })

    promptSpy.mockReturnValueOnce('Unique Project')
    fireEvent.click(await screen.findByRole('button', { name: 'New Project' }))
    await waitFor(() => {
      expect(alertSpy).toHaveBeenCalled()
    })
    expect(screen.getAllByText('Unique Project').length).toBe(2)
    promptSpy.mockRestore()
    alertSpy.mockRestore()
  })
})
