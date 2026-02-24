import { fireEvent, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { VocabularyPage } from './VocabularyPage'
import { renderWithProviders } from '../test/testUtils'
import { MockRuntimeApi } from '../api/mockRuntimeApi'
import type { VisualizerNode } from '../api/runtimeApi'

function countElements(node: VisualizerNode): number {
  let total = 0
  const stack = [...(node.linguistic_elements || [])]
  while (stack.length) {
    const current = stack.shift()
    if (!current) continue
    total += 1
    for (const child of current.linguistic_elements || []) stack.push(child)
  }
  return total
}

describe('VocabularyPage', () => {
  it('shows only analyzed files', async () => {
    renderWithProviders(<VocabularyPage />)
    expect(await screen.findByText('sample.mp4')).toBeInTheDocument()
    expect(screen.queryByText('draft.mp3')).not.toBeInTheDocument()
  })

  it('enables Visualizer button after selecting analyzed row', async () => {
    renderWithProviders(<VocabularyPage />)
    const visualizerBtn = await screen.findByRole('button', { name: 'Visualizer' })
    expect(visualizerBtn).toBeDisabled()

    const checkboxes = await screen.findAllByRole('checkbox')
    fireEvent.click(checkboxes[0])
    expect(visualizerBtn).toBeEnabled()
  })

  it('shows items count from contract linguistic elements', async () => {
    const api = new MockRuntimeApi()
    const payload = await api.getVisualizerPayload('doc-1')
    const expected = Object.values(payload).reduce((acc, root) => acc + countElements(root), 0)

    renderWithProviders(<VocabularyPage />, api)
    expect(await screen.findByText(String(expected))).toBeInTheDocument()
  })
})
