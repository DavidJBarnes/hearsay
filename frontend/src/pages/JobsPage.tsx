import { useEffect, useState } from 'react';
import { client } from '../api/client';
import type { Job } from '../api/types';

// Lists batch jobs with live status, refreshing on an interval, and lets the
// user enqueue a quick TTS job.
export function JobsPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [text, setText] = useState('A batch synthesis job.');
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    try {
      setJobs(await client.listJobs());
    } catch (e) {
      setError((e as Error).message);
    }
  }

  useEffect(() => {
    void refresh();
    const id = setInterval(() => void refresh(), 2000);
    return () => clearInterval(id);
  }, []);

  async function enqueue() {
    setError(null);
    try {
      await client.createJob('tts', { input: text, voice: 'af_heart' });
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <section className="page">
      <h2>Jobs</h2>
      <div className="row">
        <input
          aria-label="job text"
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <button onClick={enqueue}>Enqueue TTS job</button>
      </div>
      <table className="jobs-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>Type</th>
            <th>Engine</th>
            <th>Status</th>
            <th>Processing (s)</th>
          </tr>
        </thead>
        <tbody>
          {jobs.map((j) => (
            <tr key={j.id} data-testid="job-row">
              <td className="mono">{j.id.slice(0, 8)}</td>
              <td>{j.type}</td>
              <td>{j.engine}</td>
              <td>
                <span className={`status status-${j.status}`}>{j.status}</span>
              </td>
              <td>{j.timing.processing_s ? j.timing.processing_s.toFixed(2) : '—'}</td>
            </tr>
          ))}
          {jobs.length === 0 && (
            <tr>
              <td colSpan={5} className="muted">
                No jobs yet.
              </td>
            </tr>
          )}
        </tbody>
      </table>
      {error && <p className="error" role="alert">{error}</p>}
    </section>
  );
}
