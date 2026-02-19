import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { VocabularyPage } from './VocabularyPage'
import { renderWithProviders } from '../test/testUtils'

describe('VocabularyPage', () => {
  it('shows only analyzed files', async () => {
    renderWithProviders(<VocabularyPage />)
    expect(await screen.findByText('sample.mp4')).toBeInTheDocument()
    expect(screen.queryByText('draft.mp3')).not.toBeInTheDocument()
  })
})

