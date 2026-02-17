import { fireEvent, screen, waitFor } from '@testing-library/react'
import { VisualizerPage } from './VisualizerPage'
import { renderWithProviders } from '../test/testUtils'

describe('VisualizerPage', () => {
  it('renders visualizer tree payload', async () => {
    renderWithProviders(<VisualizerPage />)

    await waitFor(() => {
      expect(screen.getByText('She trusted him.')).toBeInTheDocument()
    })
    const sentenceStrong = screen.getByText('Sentence', { selector: 'strong' })
    expect(sentenceStrong.parentElement?.textContent).toContain('She trusted him.')
    expect(sentenceStrong.parentElement?.textContent).toContain('[B1]')

    const wordStrong = screen.getByText('Word', { selector: 'strong' })
    expect(wordStrong.parentElement?.textContent).toContain('trusted')
  })

  it('applies node edit and updates rendered content', async () => {
    renderWithProviders(<VisualizerPage />)

    await waitFor(() => {
      const phraseStrong = screen.getByText('Phrase', { selector: 'strong' })
      expect(phraseStrong.parentElement?.textContent).toContain('trusted him')
    })

    fireEvent.change(screen.getByLabelText(/Node ID/), { target: { value: 'p1' } })
    fireEvent.change(screen.getByLabelText(/New Content/), { target: { value: 'trusted them' } })
    fireEvent.click(screen.getByRole('button', { name: 'Apply Edit' }))

    await waitFor(() => {
      expect(screen.getByText('Edit applied.')).toBeInTheDocument()
    })
    const phraseStrong = screen.getByText('Phrase', { selector: 'strong' })
    expect(phraseStrong.parentElement?.textContent).toContain('trusted them')
  })
})
