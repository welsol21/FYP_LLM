import { fireEvent, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { toExportRows, VocabularyPage, type VocabRow } from './VocabularyPage'
import { renderWithProviders } from '../test/testUtils'
import { MockRuntimeApi } from '../api/mockRuntimeApi'
import type { VisualizerNode, VisualizerPayload } from '../api/runtimeApi'

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

  it('exports selected provider translation rows', async () => {
    const payload: VisualizerPayload = {
      'Sentence one.': {
        node_id: 's1',
        type: 'Sentence',
        content: 'Sentence one.',
        tense: '',
        linguistic_notes: [],
        part_of_speech: 'sentence',
        linguistic_elements: [
          {
            node_id: 'w1',
            type: 'Word',
            content: 'She',
            tense: '',
            linguistic_notes: [],
            part_of_speech: 'pronoun',
            linguistic_elements: [],
            translations: {
              backend_m2m100: { text: 'Она' },
              gpt: { text: 'Она (GPT)' },
            },
          },
        ],
      },
    }
    const row: VocabRow = {
      id: 'row-1',
      project: 'Demo',
      file: 'sample.mp4',
      items: 1,
      created: 'Feb 18, 2026',
      documentId: 'doc-1',
      payload,
      translationProvider: 'gpt',
    }
    const rows = toExportRows(row)
    expect(rows[0].translation_provider).toBe('gpt')
    expect(rows[0].translation).toBe('Она (GPT)')
  })
})
