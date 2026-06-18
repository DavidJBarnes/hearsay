import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const listVoices = vi.fn();
const listJobs = vi.fn();
const metricsText = vi.fn();

// The pages do network work on mount; stub the client so App renders cleanly.
vi.mock('./api/client', () => ({
  getApiKey: () => '',
  setApiKey: vi.fn(),
  client: {
    listVoices: () => listVoices(),
    listJobs: () => listJobs(),
    metricsText: () => metricsText(),
  },
}));

import { App } from './App';

describe('App', () => {
  beforeEach(() => {
    listVoices.mockResolvedValue([]);
    listJobs.mockResolvedValue([]);
    metricsText.mockResolvedValue('');
  });

  it('renders the TTS playground by default', () => {
    render(<App />);
    expect(screen.getByRole('heading', { name: 'TTS Playground' })).toBeInTheDocument();
  });

  it('switches tabs', async () => {
    render(<App />);
    await userEvent.click(screen.getByRole('button', { name: 'Voice Library' }));
    expect(screen.getByRole('heading', { name: 'Voice Library' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Metrics' }));
    expect(screen.getByRole('heading', { name: 'Metrics' })).toBeInTheDocument();
  });
});
