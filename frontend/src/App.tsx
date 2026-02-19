import { NavLink, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { FilesPage } from './pages/FilesPage'
import { AnalyzePage } from './pages/AnalyzePage'
import { ProjectsPage } from './pages/ProjectsPage'
import { VisualizerPage } from './pages/VisualizerPage'
import { VocabularyPage } from './pages/VocabularyPage'
import { ConfigPage } from './pages/ConfigPage'
import { NewProjectPage } from './pages/NewProjectPage'
import { NewFilePage } from './pages/NewFilePage'
import { AnalyzeListPage } from './pages/AnalyzeListPage'

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
          <NavLink to="/config" className={({ isActive }) => (isActive ? 'top-link active' : 'top-link')}>
            Config
          </NavLink>
        </div>
      </header>
      <main className="screen">
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
      </main>
      <nav className="bottom-nav" aria-label="Primary">
        <MenuLink to="/" label="Media" />
        <MenuLink to="/analyze" label="Analyze" />
        <MenuLink to="/vocabulary" label="Vocabulary" />
      </nav>
    </div>
  )
}
