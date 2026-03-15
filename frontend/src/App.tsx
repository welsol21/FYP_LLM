import { NavLink, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { FilesPage } from './pages/FilesPage'
import { AnalyzePage } from './pages/AnalyzePage'
import { ProjectsPage } from './pages/ProjectsPage'
import { VisualizerPage } from './pages/VisualizerPage'
import { VocabularyPage } from './pages/VocabularyPage'
import { ConfigPage } from './pages/ConfigPage'
import { NewProjectPage } from './pages/NewProjectPage'
import { NewFilePage } from './pages/NewFilePage'
import { AnalyzeListPage } from './pages/AnalyzeListPage'
import { PwaInstallButton } from './components/PwaInstallButton'
import { ErrorBoundary } from './components/ErrorBoundary'
import { resolveClientMode } from './lib/clientMode'
import { ensureDesktopBootstrap, subscribeDesktopBootstrap } from './lib/desktopBootstrap'
import { recordRuntimeDiagnostic } from './lib/runtimeDiagnostics'

function MenuLink({ to, label }: { to: string; label: string }) {
  return (
    <NavLink to={to} className={({ isActive }) => (isActive ? 'bottom-link active' : 'bottom-link')}>
      {label}
    </NavLink>
  )
}

export default function App() {
  const navigate = useNavigate()
  const location = useLocation()
  const canGoBack = location.pathname !== '/'
  const pageTitleByPath: Record<string, string> = {
    '/': 'Media',
    '/files': 'Files',
    '/analyze': 'Analyze',
    '/analyze-list': 'Analyze Files',
    '/vocabulary': 'Vocabulary',
    '/visualizer': 'Linguistic Visualizer',
    '/config': 'Config',
    '/new-project': 'New Project',
    '/new-file': 'New File',
  }
  const pageTitle = pageTitleByPath[location.pathname] ?? 'ELA'
  const clientMode = resolveClientMode()
  const [bootstrapError, setBootstrapError] = useState<string>('')

  useEffect(() => {
    recordRuntimeDiagnostic('router', 'location.change', {
      path: location.pathname,
      search: location.search,
      hash: location.hash,
    })
  }, [location.pathname, location.search, location.hash])

  useEffect(() => {
    if (clientMode !== 'desktop') return
    void ensureDesktopBootstrap()
    return subscribeDesktopBootstrap((s) => {
      setBootstrapError(s.status === 'error' ? s.error : '')
    })
  }, [clientMode])

  return (
    <div className="app-shell">
      {bootstrapError ? (
        <div className="bootstrap-error-banner" role="alert">
          Desktop runtime failed to load: {bootstrapError}
        </div>
      ) : null}
      <header className="top-bar">
        <button
          type="button"
          className="back-btn"
          onClick={() => navigate(-1)}
          disabled={!canGoBack}
          aria-label="Back"
        >
          Back
        </button>
        <h1 className="top-title">{pageTitle}</h1>
        <div className="top-actions">
          {clientMode === 'pwa' ? <PwaInstallButton /> : null}
          <NavLink to="/config" className={({ isActive }) => (isActive ? 'top-link active' : 'top-link')}>
            Config
          </NavLink>
        </div>
      </header>
      <main className="screen">
        <ErrorBoundary>
          <Routes>
            <Route path="/" element={<ProjectsPage />} />
            <Route path="/files" element={<FilesPage />} />
            <Route path="/analyze" element={<AnalyzePage />} />
            <Route path="/analyze-list" element={<AnalyzeListPage />} />
            <Route path="/vocabulary" element={<VocabularyPage />} />
            <Route path="/visualizer" element={<VisualizerPage />} />
            <Route path="/config" element={<ConfigPage />} />
            <Route path="/new-project" element={<NewProjectPage />} />
            <Route path="/new-file" element={<NewFilePage />} />
          </Routes>
        </ErrorBoundary>
      </main>
      <nav className="bottom-nav" aria-label="Primary">
        <MenuLink to="/" label="Media" />
        <MenuLink to="/analyze" label="Analyze" />
        <MenuLink to="/vocabulary" label="Vocabulary" />
      </nav>
    </div>
  )
}
