import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const listJobs = vi.fn();
const createJob = vi.fn();

vi.mock('../api/client', () => ({
  client: {
    listJobs: () => listJobs(),
    createJob: (...a: unknown[]) => createJob(...a),
  },
}));

import { JobsPage } from './JobsPage';

describe('JobsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listJobs.mockResolvedValue([
      {
        id: 'abcdef123456',
        type: 'tts',
        engine: 'kokoro',
        status: 'completed',
        timing: { processing_s: 0.42 },
      },
    ]);
    createJob.mockResolvedValue({ id: 'new' });
  });

  it('renders job rows with status and timing', async () => {
    render(<JobsPage />);
    await waitFor(() => expect(screen.getByText('kokoro')).toBeInTheDocument());
    expect(screen.getByText('completed')).toBeInTheDocument();
    expect(screen.getByText('0.42')).toBeInTheDocument();
  });

  it('enqueues a TTS job', async () => {
    render(<JobsPage />);
    await userEvent.click(screen.getByRole('button', { name: 'Enqueue TTS job' }));
    await waitFor(() =>
      expect(createJob).toHaveBeenCalledWith('tts', expect.objectContaining({ voice: 'af_heart' })),
    );
  });

  it('shows an empty state', async () => {
    listJobs.mockResolvedValue([]);
    render(<JobsPage />);
    await waitFor(() => expect(screen.getByText('No jobs yet.')).toBeInTheDocument());
  });

  it('surfaces list errors', async () => {
    listJobs.mockRejectedValueOnce(new Error('down'));
    render(<JobsPage />);
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('down'));
  });
});
