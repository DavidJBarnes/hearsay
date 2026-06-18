import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { RealtimeMessage } from '../api/types';

const transcribe = vi.fn();

vi.mock('../api/client', () => ({
  client: { transcribe: (...args: unknown[]) => transcribe(...args) },
}));

// Stub LiveMic so we can drive realtime messages without audio APIs.
let emit: (m: RealtimeMessage) => void = () => {};
vi.mock('../components/LiveMic', () => ({
  LiveMic: ({ onMessage }: { onMessage: (m: RealtimeMessage) => void }) => {
    emit = onMessage;
    return <div data-testid="live-mic-stub" />;
  },
}));

import { SttPage } from './SttPage';

describe('SttPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    transcribe.mockResolvedValue({
      text: 'a transcript',
      language: 'en',
      duration: 1,
      segments: [{ start: 0, end: 1, text: 'a transcript', speaker: 'SPEAKER_00' }],
      diarization: null,
    });
  });

  it('errors when transcribing with no file', async () => {
    render(<SttPage />);
    await userEvent.click(screen.getByRole('button', { name: 'Transcribe' }));
    expect(screen.getByRole('alert')).toHaveTextContent('Choose a file first');
  });

  it('uploads a file and renders segments', async () => {
    render(<SttPage />);
    const file = new File([new Uint8Array([1, 2, 3])], 'a.wav', { type: 'audio/wav' });
    await userEvent.upload(screen.getByLabelText('audio file'), file);
    await userEvent.click(screen.getByLabelText('Diarize'));
    await userEvent.click(screen.getByRole('button', { name: 'Transcribe' }));
    await waitFor(() => expect(screen.getByText('a transcript')).toBeInTheDocument());
    expect(transcribe).toHaveBeenCalledWith(file, 'whisper-1', true);
    expect(screen.getByText(/SPEAKER_00/)).toBeInTheDocument();
  });

  it('renders live partial then final transcripts', async () => {
    render(<SttPage />);
    emit({ type: 'partial', text: 'hello' });
    await waitFor(() => expect(screen.getByTestId('live-text')).toHaveTextContent('hello'));
    emit({ type: 'final', text: 'hello world' });
    await waitFor(() =>
      expect(screen.getByTestId('live-text')).toHaveTextContent('hello world'),
    );
  });

  it('shows realtime errors', async () => {
    render(<SttPage />);
    emit({ type: 'error', text: 'unauthorized' });
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('unauthorized'));
  });

  it('shows an error when upload fails', async () => {
    transcribe.mockRejectedValueOnce(new Error('bad audio'));
    render(<SttPage />);
    const file = new File([new Uint8Array([1])], 'a.wav', { type: 'audio/wav' });
    await userEvent.upload(screen.getByLabelText('audio file'), file);
    await userEvent.click(screen.getByRole('button', { name: 'Transcribe' }));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('bad audio'));
  });
});
