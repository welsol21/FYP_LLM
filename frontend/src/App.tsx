import { NavLink, Route, Routes } from 'react-router-dom'
import { FilesPage } from './pages/FilesPage'
import { AnalyzePage } from './pages/AnalyzePage'
import { ProjectsPage } from './pages/ProjectsPage'
import { VisualizerPage } from './pages/VisualizerPage'
import { VocabularyPage } from './pages/VocabularyPage'

function MenuLink({ to, label }: { to: string; label: string }) {
  return (
    <NavLink to={to} className={({ isActive }) => (isActive ? 'menu-link active' : 'menu-link')}>
      {label}
    </NavLink>
  )
}

export default function App() {
  return (
    <div className="layout">
      <aside className="sidebar">
        <h1>ELA UI</h1>
        <nav>
          <MenuLink to="/" label="Projects" />
          <MenuLink to="/files" label="Files" />
          <MenuLink to="/analyze" label="Analyze" />
          <MenuLink to="/vocabulary" label="Vocabulary" />
          <MenuLink to="/visualizer" label="Visualizer" />
        </nav>
      </aside>
      <main className="content">
        <Routes>
          <Route path="/" element={<ProjectsPage />} />
          <Route path="/files" element={<FilesPage />} />
          <Route path="/analyze" element={<AnalyzePage />} />
          <Route path="/vocabulary" element={<VocabularyPage />} />
          <Route path="/visualizer" element={<VisualizerPage />} />
        </Routes>
      </main>
    </div>
  )
}
