import { screen } from '@testing-library/react'
import { BackendJobsTable } from './BackendJobsTable'
import { renderWithProviders } from '../test/testUtils'

describe('BackendJobsTable', () => {
  it('renders empty state and rows', () => {
    const { rerender } = renderWithProviders(<BackendJobsTable jobs={[]} />)
    expect(screen.getByText('No backend jobs.')).toBeInTheDocument()

    rerender(
      <BackendJobsTable
        jobs={[
          {
            id: 'job-1',
            status: 'queued',
            media_path: '/tmp/a.mp4',
            duration_seconds: 1600,
            size_bytes: 200,
          },
        ]}
      />,
    )

    expect(screen.getByText('job-1')).toBeInTheDocument()
    expect(screen.getByText('/tmp/a.mp4')).toBeInTheDocument()
  })
})
