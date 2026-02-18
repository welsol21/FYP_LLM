import { fireEvent, screen, waitFor } from '@testing-library/react'
import { AnalyzePage } from './AnalyzePage'
import { renderWithProviders } from '../test/testUtils'

describe('AnalyzePage', () => {
  it('shows backend queue feedback and syncs completed result to visualizer-ready state', async () => {
    renderWithProviders(<AnalyzePage />)
    await waitFor(() => {
      expect(screen.getByText(/Project:\s*proj-1/i)).toBeInTheDocument()
    })

    fireEvent.change(screen.getByLabelText(/Duration/), { target: { value: '1800' } })
    fireEvent.change(screen.getByLabelText(/Size \(bytes\)/), { target: { value: '314572800' } })
    fireEvent.click(screen.getByRole('button', { name: 'Start' }))

    await waitFor(() => {
      expect(screen.getByText('Queued for backend processing')).toBeInTheDocument()
    })
    expect(screen.getByText(/Job ID:/)).toBeInTheDocument()
    expect(screen.getByRole('cell', { name: /job-1/i })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Check status' }))
    await waitFor(() => {
      expect(screen.getByLabelText('backend-job-controls')).toHaveTextContent(/Status:\s*processing/i)
    })

    fireEvent.click(screen.getByRole('button', { name: 'Check status' }))
    await waitFor(() => {
      expect(screen.getByText(/Backend result synced to local document tables/i)).toBeInTheDocument()
    })
    expect(screen.getByRole('button', { name: 'Open Visualizer' })).toBeInTheDocument()
  })
})
