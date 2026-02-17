import { fireEvent, screen, waitFor } from '@testing-library/react'
import { VisualizerPage } from './VisualizerPage'
import { renderWithProviders } from '../test/testUtils'

describe('VisualizerPage', () => {
  it('renders visualizer tree payload', async () => {
    renderWithProviders(<VisualizerPage />)

    await waitFor(() => {
      expect(screen.getAllByText('Although she had been warned several times, she still chose to ignore the evidence, which eventually led to a costly mistake that could have been avoided.').length).toBeGreaterThan(0)
    })
    expect(screen.getAllByText('B2').length).toBeGreaterThan(0)
    expect(screen.getAllByText('still chose to ignore the evidence').length).toBeGreaterThan(0)
    expect(screen.getByText(/CEFR:/)).toBeInTheDocument()
  })

  it('applies node edit and updates rendered content', async () => {
    renderWithProviders(<VisualizerPage />)

    await waitFor(() => {
      expect(screen.getByText('Verb Phrase')).toBeInTheDocument()
      expect(screen.getAllByText('still chose to ignore the evidence').length).toBeGreaterThan(0)
    })

    fireEvent.change(screen.getByLabelText(/Node ID/), { target: { value: 'p1' } })
    fireEvent.change(screen.getByLabelText(/New Content/), { target: { value: 'trusted them' } })
    fireEvent.click(screen.getByRole('button', { name: 'Apply Edit' }))

    await waitFor(() => {
      expect(screen.getByText('Edit applied.')).toBeInTheDocument()
    })
  })
})
