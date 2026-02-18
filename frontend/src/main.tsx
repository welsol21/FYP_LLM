import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import { ApiContext } from './api/apiContext'
import { HttpRuntimeApi } from './api/httpRuntimeApi'
import { MockRuntimeApi } from './api/mockRuntimeApi'
import './styles.css'

const runtimeApi = (import.meta.env.VITE_USE_MOCK_API === '1')
  ? new MockRuntimeApi()
  : new HttpRuntimeApi()

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ApiContext.Provider value={runtimeApi}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </ApiContext.Provider>
  </React.StrictMode>,
)
