import { fireEvent, screen, waitFor } from '@testing-library/react'
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
})
