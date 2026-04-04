import { NavLink, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { useEffect } from 'react'
import { FilesPage } from './pages/FilesPage'
import { AnalyzePage } from './pages/AnalyzePage'
import { ProjectsPage } from './pages/ProjectsPage'
import { VisualizerPage } from './pages/VisualizerPage'
import { VocabularyPage } from './pages/VocabularyPage'
import { ConfigPage } from './pages/ConfigPage'
import { AboutPage } from './pages/AboutPage'
import { NewProjectPage } from './pages/NewProjectPage'
import { NewFilePage } from './pages/NewFilePage'
import { AnalyzeListPage } from './pages/AnalyzeListPage'
import { PwaInstallButton } from './components/PwaInstallButton'
import { ErrorBoundary } from './components/ErrorBoundary'
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
    '/about': 'About',
    '/new-project': 'New Project',
    '/new-file': 'New File',
  }
  const pageTitle = pageTitleByPath[location.pathname] ?? 'ELA'

  useEffect(() => {
    recordRuntimeDiagnostic('router', 'location.change', {
      path: location.pathname,
      search: location.search,
      hash: location.hash,
    })
  }, [location.pathname, location.search, location.hash])

  return (
    <div className="app-shell">
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
          <PwaInstallButton />
          <NavLink to="/about" className={({ isActive }) => (isActive ? 'top-link active' : 'top-link')}>
            About
          </NavLink>
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
        <Route path="/about" element={<AboutPage />} />
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
