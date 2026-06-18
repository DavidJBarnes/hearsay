import { useEffect, useState } from 'react';
import { client } from '../api/client';
import { gauge, parseMetrics, sumByName, type MetricSample } from '../api/metrics';

// Renders key telemetry: RTF/TTFA/latency counts, queue depth, and GPU stats.
export function MetricsPage() {
  const [samples, setSamples] = useState<MetricSample[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    try {
      setSamples(parseMetrics(await client.metricsText()));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  useEffect(() => {
    void refresh();
    const id = setInterval(() => void refresh(), 3000);
    return () => clearInterval(id);
  }, []);

  const latencyCount = sumByName(samples, 'hearsay_request_latency_seconds_count');
  const rtfCount = sumByName(samples, 'hearsay_engine_rtf_count');
  const ttfaCount = sumByName(samples, 'hearsay_engine_ttfa_seconds_count');
  const queue = gauge(samples, 'hearsay_queue_depth');
  const gpuMemUsed = gauge(samples, 'hearsay_gpu_memory_used_bytes');
  const gpuUtil = gauge(samples, 'hearsay_gpu_utilization_ratio');

  return (
    <section className="page">
      <h2>Metrics</h2>
      <div className="metrics-grid">
        <Stat label="Requests observed" value={latencyCount} />
        <Stat label="RTF observations" value={rtfCount} />
        <Stat label="TTFA observations" value={ttfaCount} />
      </div>

      <h3>Queue depth</h3>
      <ul data-testid="queue-list">
        {queue.length === 0 && <li className="muted">No queue data.</li>}
        {queue.map((s, i) => (
          <li key={i}>
            {s.labels.status}: {s.value}
          </li>
        ))}
      </ul>

      <h3>GPU</h3>
      <ul data-testid="gpu-list">
        {gpuMemUsed.length === 0 && <li className="muted">No GPU data.</li>}
        {gpuMemUsed.map((s, i) => (
          <li key={i}>
            Device {s.labels.device}: {(s.value / 1e9).toFixed(2)} GB used,{' '}
            {((gpuUtil.find((u) => u.labels.device === s.labels.device)?.value ?? 0) * 100).toFixed(
              0,
            )}
            % util
          </li>
        ))}
      </ul>

      {error && <p className="error" role="alert">{error}</p>}
    </section>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="stat">
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
    </div>
  );
}
