import type { BackendJob } from '../api/runtimeApi'

type Props = {
  jobs: BackendJob[]
}

export function BackendJobsTable({ jobs }: Props) {
  return (
    <section className="card" aria-label="backend-jobs">
      <h2>Backend Jobs</h2>
      {jobs.length === 0 ? (
        <p>No backend jobs.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Status</th>
              <th>Path</th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((job) => (
              <tr key={job.id}>
                <td>{job.id}</td>
                <td>{job.status}</td>
                <td>{job.media_path}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}
