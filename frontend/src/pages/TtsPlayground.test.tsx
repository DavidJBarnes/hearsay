import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const listVoices = vi.fn();
const synthesize = vi.fn();

vi.mock('../api/client', () => ({
  client: {
    listVoices: () => listVoices(),
    synthesize: (req: unknown) => synthesize(req),
    synthesizeStreamUrl: () => '/v1/audio/speech',
  },
}));

import { TtsPlayground } from './TtsPlayground';

describe('TtsPlayground', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listVoices.mockResolvedValue([{ id: '1', name: 'MyClone', type: 'cloned' }]);
    synthesize.mockResolvedValue(new Blob(['audio']));
  });

  it('lists cloned voices alongside presets', async () => {
    render(<TtsPlayground />);
    await waitFor(() => expect(screen.getByRole('option', { name: 'MyClone' })).toBeInTheDocument());
  });

  it('generates audio, shows a player, and auto-plays it', async () => {
    render(<TtsPlayground />);
    await userEvent.click(screen.getByRole('button', { name: 'Speak' }));
    await waitFor(() => expect(screen.getByTestId('audio-player')).toBeInTheDocument());
    expect(synthesize).toHaveBeenCalledOnce();
    await waitFor(() =>
      expect(window.HTMLMediaElement.prototype.play).toHaveBeenCalled(),
    );
  });

  it('shows an error when synthesis fails', async () => {
    synthesize.mockRejectedValueOnce(new Error('boom'));
    render(<TtsPlayground />);
    await userEvent.click(screen.getByRole('button', { name: 'Speak' }));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('boom'));
  });

  it('streams audio and reports byte count', async () => {
    const reader = {
      read: vi
        .fn()
        .mockResolvedValueOnce({ done: false, value: new Uint8Array([1, 2, 3]) })
        .mockResolvedValueOnce({ done: true, value: undefined }),
    };
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, body: { getReader: () => reader } }),
    );
    render(<TtsPlayground />);
    await userEvent.click(screen.getByRole('button', { name: 'Stream' }));
    await waitFor(() => expect(screen.getByText(/Streamed 3 bytes/)).toBeInTheDocument());
    vi.unstubAllGlobals();
  });

  it('surfaces a streaming failure', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 500, body: null }));
    render(<TtsPlayground />);
    await userEvent.click(screen.getByRole('button', { name: 'Stream' }));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('stream failed'));
    vi.unstubAllGlobals();
  });
});
