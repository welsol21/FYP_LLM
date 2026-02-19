import { screen } from '@testing-library/react'
import { RuntimeStatusCard } from './RuntimeStatusCard'
import { renderWithProviders } from '../test/testUtils'

describe('RuntimeStatusCard', () => {
  it('renders disabled reason when feature is blocked', () => {
    renderWithProviders(
      <RuntimeStatusCard
        uiState={{
          runtime_mode: 'offline',
          deployment_mode: 'distributed',
          badges: {
            mode: 'Mode: offline',
            deployment: 'Deployment: distributed',
            phonetic: 'Phonetic: off',
          },
          features: {
            phonetic: {
              enabled: false,
              reason_if_disabled: 'Unavailable in offline mode (license/deployment gate).',
            },
            db_persistence: {
              enabled: false,
              reason_if_disabled: 'Unavailable in offline mode (requires backend connectivity).',
            },
          },
        }}
      />,
    )

    expect(screen.getByText(/Mode: offline/)).toBeInTheDocument()
    expect(screen.getByText(/Phonetic: off/)).toBeInTheDocument()
    expect(screen.getByText(/phonetic/i, { selector: 'strong' })).toBeInTheDocument()
    expect(screen.getByText(/license\/deployment gate/)).toBeInTheDocument()
  })
})
