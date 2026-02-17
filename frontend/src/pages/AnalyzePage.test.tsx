import { fireEvent, screen, waitFor } from '@testing-library/react'
import { AnalyzePage } from './AnalyzePage'
import { renderWithProviders } from '../test/testUtils'

describe('AnalyzePage', () => {
  it('shows backend queue feedback and adds job row for large media', async () => {
    renderWithProviders(<AnalyzePage />)

    fireEvent.change(screen.getByLabelText(/Duration/), { target: { value: '1800' } })
    fireEvent.change(screen.getByLabelText(/Size \(bytes\)/), { target: { value: '314572800' } })
    fireEvent.click(screen.getByRole('button', { name: 'Start' }))

    await waitFor(() => {
      expect(screen.getByText('Queued for backend processing')).toBeInTheDocument()
    })
    expect(screen.getByText(/Job ID:/)).toBeInTheDocument()
    expect(screen.getByRole('cell', { name: /job-1/i })).toBeInTheDocument()
  })
})
