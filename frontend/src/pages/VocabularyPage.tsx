import { Link } from 'react-router-dom'

export function VocabularyPage() {
  return (
    <section className="card compact-card">
      <p>Open linguistic visualizer for selected sentence.</p>
      <Link to="/visualizer">Open Visualizer</Link>
    </section>
  )
}
