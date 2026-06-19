import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const openRealtime = vi.fn();

vi.mock('../api/client', () => ({
  client: { openRealtime: (...a: unknown[]) => openRealtime(...a) },
}));

import { LiveMic } from './LiveMic';

interface FakeProcessor {
  onaudioprocess: ((ev: unknown) => void) | null;
  connect: ReturnType<typeof vi.fn>;
}

function installAudioMocks() {
  const socket = { send: vi.fn(), finish: vi.fn(), close: vi.fn() };
  openRealtime.mockReturnValue(socket);
  const track = { stop: vi.fn() };
  const stream = { getTracks: () => [track] };
  const getUserMedia = vi.fn().mockResolvedValue(stream);
  vi.stubGlobal('navigator', { mediaDevices: { getUserMedia } });

  const processor: FakeProcessor = { onaudioprocess: null, connect: vi.fn() };
  class FakeAudioContext {
    sampleRate = 48000;
    createMediaStreamSource = vi.fn(() => ({ connect: vi.fn() }));
    createScriptProcessor = vi.fn(() => processor);
    destination = {};
    close = vi.fn();
  }
  vi.stubGlobal('AudioContext', FakeAudioContext as unknown as typeof AudioContext);
  return { socket, track, processor };
}

describe('LiveMic', () => {
  beforeEach(() => vi.clearAllMocks());

  it('starts and stops recording, streaming PCM frames', async () => {
    const { socket, track, processor } = installAudioMocks();
    render(<LiveMic onMessage={vi.fn()} />);

    await userEvent.click(screen.getByRole('button', { name: /Start recording/ }));
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /Stop recording/ })).toBeInTheDocument(),
    );

    // Drive one audio frame through the processor callback.
    processor.onaudioprocess?.({
      inputBuffer: { getChannelData: () => new Float32Array([0.1, -0.1, 0.2]) },
    });
    expect(socket.send).toHaveBeenCalled();

    await userEvent.click(screen.getByRole('button', { name: /Stop recording/ }));
    expect(socket.finish).toHaveBeenCalled(); // graceful flush, not a hard close
    expect(track.stop).toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it('reports an unavailable mic in a secure context', async () => {
    vi.stubGlobal('navigator', { mediaDevices: undefined });
    vi.stubGlobal('isSecureContext', true);
    render(<LiveMic onMessage={vi.fn()} />);
    await userEvent.click(screen.getByRole('button', { name: /Start recording/ }));
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(
        'Microphone not available in this browser',
      ),
    );
    vi.unstubAllGlobals();
  });

  it('explains the secure-context requirement over plain HTTP', async () => {
    vi.stubGlobal('navigator', { mediaDevices: undefined });
    vi.stubGlobal('isSecureContext', false);
    render(<LiveMic onMessage={vi.fn()} />);
    await userEvent.click(screen.getByRole('button', { name: /Start recording/ }));
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent('Live mic needs a secure context'),
    );
    vi.unstubAllGlobals();
  });
});
