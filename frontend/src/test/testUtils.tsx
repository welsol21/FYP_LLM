import type { ReactElement } from 'react'
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { ApiContext } from '../api/apiContext'
import { MockRuntimeApi } from '../api/mockRuntimeApi'
import type { RuntimeApi } from '../api/runtimeApi'

export function renderWithProviders(ui: ReactElement, api?: RuntimeApi) {
  const runtimeApi = api ?? new MockRuntimeApi()
  return render(
    <ApiContext.Provider value={runtimeApi}>
      <MemoryRouter>{ui}</MemoryRouter>
    </ApiContext.Provider>,
  )
}
