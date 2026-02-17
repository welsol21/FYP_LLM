import { createContext, useContext } from 'react'
import { MockRuntimeApi } from './mockRuntimeApi'
import type { RuntimeApi } from './runtimeApi'

const defaultApi: RuntimeApi = new MockRuntimeApi()

export const ApiContext = createContext<RuntimeApi>(defaultApi)

export function useApi(): RuntimeApi {
  return useContext(ApiContext)
}
