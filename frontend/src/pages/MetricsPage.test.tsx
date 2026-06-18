import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

const metricsText = vi.fn();

vi.mock('../api/client', () => ({
  client: { metricsText: () => metricsText() },
}));

import { MetricsPage } from './MetricsPage';

const METRICS = `
hearsay_request_latency_seconds_count{route="/v1/audio/speech",method="POST"} 4
hearsay_engine_rtf_count{engine="kokoro",kind="tts"} 2
hearsay_engine_ttfa_seconds_count{engine="kokoro",kind="tts"} 2
hearsay_queue_depth{status="queued"} 1
hearsay_gpu_memory_used_bytes{device="0"} 5000000000
hearsay_gpu_utilization_ratio{device="0"} 0.5
`;

describe('MetricsPage', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders stats, queue depth, and GPU info', async () => {
    metricsText.mockResolvedValue(METRICS);
    render(<MetricsPage />);
    await waitFor(() => expect(screen.getByText('Requests observed')).toBeInTheDocument());
    expect(screen.getByTestId('queue-list')).toHaveTextContent('queued: 1');
    expect(screen.getByTestId('gpu-list')).toHaveTextContent('5.00 GB used');
    expect(screen.getByTestId('gpu-list')).toHaveTextContent('50% util');
  });

  it('shows empty states without data', async () => {
    metricsText.mockResolvedValue('');
    render(<MetricsPage />);
    await waitFor(() => expect(screen.getByText('No queue data.')).toBeInTheDocument());
    expect(screen.getByText('No GPU data.')).toBeInTheDocument();
  });

  it('surfaces fetch errors', async () => {
    metricsText.mockRejectedValueOnce(new Error('metrics down'));
    render(<MetricsPage />);
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('metrics down'));
  });
});
