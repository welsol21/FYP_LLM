import { NavLink, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { FilesPage } from './pages/FilesPage'
import { AnalyzePage } from './pages/AnalyzePage'
import { ProjectsPage } from './pages/ProjectsPage'
import { VisualizerPage } from './pages/VisualizerPage'
import { VocabularyPage } from './pages/VocabularyPage'

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
        <div className="top-actions">
          <NavLink to="/files" className={({ isActive }) => (isActive ? 'top-link active' : 'top-link')}>
            Files
          </NavLink>
          <NavLink
            to="/visualizer"
            className={({ isActive }) => (isActive ? 'top-link active' : 'top-link')}
          >
            Visualizer
          </NavLink>
        </div>
      </header>
      <main className="screen">
        <Routes>
          <Route path="/" element={<ProjectsPage />} />
          <Route path="/files" element={<FilesPage />} />
          <Route path="/analyze" element={<AnalyzePage />} />
          <Route path="/vocabulary" element={<VocabularyPage />} />
          <Route path="/visualizer" element={<VisualizerPage />} />
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
