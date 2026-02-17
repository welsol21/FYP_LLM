export function FilesPage() {
  return (
    <section className="card">
      <h1>Files</h1>
      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>Settings</th>
            <th>Updated</th>
            <th>Analyzed</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>sample.mp4</td>
            <td>GPT / Bilingual</td>
            <td>Feb 17, 2026</td>
            <td>yes</td>
          </tr>
        </tbody>
      </table>
    </section>
  )
}
