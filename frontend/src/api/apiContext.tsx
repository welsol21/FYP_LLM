import { createContext, useContext } from 'react'
import type { RuntimeApi } from './runtimeApi'

export const ApiContext = createContext<RuntimeApi | null>(null)

export function useApi(): RuntimeApi {
  const api = useContext(ApiContext)
  if (!api) {
    throw new Error('ApiContext is not provided')
  }
  return api
}
