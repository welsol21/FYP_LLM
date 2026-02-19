import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { AnalyzePage } from './AnalyzePage'
import { ApiContext } from '../api/apiContext'
import { MockRuntimeApi } from '../api/mockRuntimeApi'

describe('AnalyzePage', () => {
  it('shows compact analyze panel with selected file and submit feedback', async () => {
    const api = new MockRuntimeApi()
    render(
      <ApiContext.Provider value={api}>
        <MemoryRouter
          initialEntries={[
            {
              pathname: '/analyze',
              state: {
                selectedMedia: {
                  mediaFileId: 'file-1',
                  fileName: 'sample.mp4',
                  mediaPath: '/uploads/sample.mp4',
                  sizeBytes: 104857600,
                  durationSec: 600,
                },
              },
            },
          ]}
        >
          <AnalyzePage />
        </MemoryRouter>
      </ApiContext.Provider>,
    )
    await waitFor(() => {
      expect(screen.getByText('Demo Project')).toBeInTheDocument()
      expect(screen.getByText('sample.mp4')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: 'Start pipeline' }))

    await waitFor(() => {
      expect(screen.getByText(/File accepted for local processing/i)).toBeInTheDocument()
    })
  })
})
