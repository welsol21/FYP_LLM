import { fireEvent, screen, waitFor } from '@testing-library/react'
import { VisualizerPage } from './VisualizerPage'
import { renderWithProviders } from '../test/testUtils'

describe('VisualizerPage', () => {
  it('renders visualizer tree payload', async () => {
    renderWithProviders(<VisualizerPage />)

    await waitFor(() => {
      expect(screen.getAllByText('She should have trusted her instincts before making the decision.').length).toBeGreaterThan(0)
    })
    expect(screen.getAllByText('B2').length).toBeGreaterThan(0)
    expect(screen.getAllByText('should have trusted her instincts').length).toBeGreaterThan(0)
    expect(screen.getAllByText(/CEFR:/).length).toBeGreaterThan(0)
  })

  it('applies node edit and updates rendered content', async () => {
    renderWithProviders(<VisualizerPage />)

    await waitFor(() => {
      expect(screen.getByText('verb phrase')).toBeInTheDocument()
      expect(screen.getAllByText('should have trusted her instincts').length).toBeGreaterThan(0)
    })

    fireEvent.change(screen.getByLabelText(/Node ID/), { target: { value: 'n4' } })
    fireEvent.change(screen.getByLabelText(/New Content/), { target: { value: 'trusted them' } })
    fireEvent.click(screen.getByRole('button', { name: 'Apply Edit' }))

    await waitFor(() => {
      expect(screen.getByText('Edit applied.')).toBeInTheDocument()
    })
  })
})
