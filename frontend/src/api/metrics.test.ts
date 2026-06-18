import { describe, expect, it } from 'vitest';
import { gauge, parseMetrics, sumByName } from './metrics';

const SAMPLE = `
# HELP hearsay_queue_depth depth
# TYPE hearsay_queue_depth gauge
hearsay_queue_depth{status="queued"} 3
hearsay_queue_depth{status="running"} 1
hearsay_request_latency_seconds_count{route="/v1/audio/speech",method="POST"} 5
hearsay_gpu_utilization_ratio{device="0"} 0.42
not_a_metric_line
malformed{label} 1
gauge_no_value{a="b"}
`;

describe('parseMetrics', () => {
  it('parses labelled samples and ignores comments/garbage', () => {
    const samples = parseMetrics(SAMPLE);
    const queued = samples.find(
      (s) => s.name === 'hearsay_queue_depth' && s.labels.status === 'queued',
    );
    expect(queued?.value).toBe(3);
    expect(samples.some((s) => s.name === 'not_a_metric_line')).toBe(false);
  });

  it('sums by name and selects gauges', () => {
    const samples = parseMetrics(SAMPLE);
    expect(sumByName(samples, 'hearsay_queue_depth')).toBe(4);
    expect(gauge(samples, 'hearsay_gpu_utilization_ratio')[0].labels.device).toBe('0');
  });

  it('handles empty and label-less input', () => {
    expect(parseMetrics('')).toEqual([]);
    const noLabels = parseMetrics('metric_total 7');
    expect(noLabels[0]).toMatchObject({ name: 'metric_total', labels: {}, value: 7 });
  });
});
