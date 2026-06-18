// Minimal Prometheus text-format parser for the Metrics page.
//
// We only need a handful of series, so this extracts sample lines into a flat
// list of { name, labels, value } records rather than a full model.

export interface MetricSample {
  name: string;
  labels: Record<string, string>;
  value: number;
}

export function parseMetrics(text: string): MetricSample[] {
  const samples: MetricSample[] = [];
  for (const rawLine of text.split('\n')) {
    const line = rawLine.trim();
    if (!line || line.startsWith('#')) continue;
    const match = line.match(/^([a-zA-Z_:][a-zA-Z0-9_:]*)(\{[^}]*\})?\s+(.+)$/);
    if (!match) continue;
    const [, name, labelBlock, valueStr] = match;
    const value = Number(valueStr);
    if (Number.isNaN(value)) continue;
    samples.push({ name, labels: parseLabels(labelBlock), value });
  }
  return samples;
}

function parseLabels(block?: string): Record<string, string> {
  const labels: Record<string, string> = {};
  if (!block) return labels;
  const inner = block.slice(1, -1);
  if (!inner) return labels;
  for (const pair of inner.split(',')) {
    const eq = pair.indexOf('=');
    if (eq === -1) continue;
    const key = pair.slice(0, eq).trim();
    const val = pair.slice(eq + 1).trim().replace(/^"|"$/g, '');
    labels[key] = val;
  }
  return labels;
}

export function sumByName(samples: MetricSample[], name: string): number {
  return samples.filter((s) => s.name === name).reduce((acc, s) => acc + s.value, 0);
}

export function gauge(samples: MetricSample[], name: string): MetricSample[] {
  return samples.filter((s) => s.name === name);
}
