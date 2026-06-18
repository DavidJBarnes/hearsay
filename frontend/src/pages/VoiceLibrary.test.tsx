import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const listVoices = vi.fn();
const createVoice = vi.fn();
const deleteVoice = vi.fn();

vi.mock('../api/client', () => ({
  client: {
    listVoices: () => listVoices(),
    createVoice: (...a: unknown[]) => createVoice(...a),
    deleteVoice: (id: string) => deleteVoice(id),
  },
}));

import { VoiceLibrary } from './VoiceLibrary';

describe('VoiceLibrary', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listVoices.mockResolvedValue([
      { id: '1', name: 'Alpha', engine: 'kokoro', type: 'preset' },
    ]);
    createVoice.mockResolvedValue({ id: '2', name: 'Beta', engine: 'chatterbox', type: 'cloned' });
    deleteVoice.mockResolvedValue(undefined);
  });

  it('lists existing voices', async () => {
    render(<VoiceLibrary />);
    await waitFor(() => expect(screen.getByText('Alpha')).toBeInTheDocument());
  });

  it('validates that a name is required', async () => {
    render(<VoiceLibrary />);
    await userEvent.click(screen.getByRole('button', { name: 'Create' }));
    expect(screen.getByRole('alert')).toHaveTextContent('Name is required');
  });

  it('creates a cloned voice with a reference file', async () => {
    render(<VoiceLibrary />);
    await userEvent.type(screen.getByLabelText('voice name'), 'Beta');
    const file = new File([new Uint8Array([1, 2])], 'ref.wav', { type: 'audio/wav' });
    await userEvent.upload(screen.getByLabelText('reference sample'), file);
    await userEvent.click(screen.getByRole('button', { name: 'Create' }));
    await waitFor(() => expect(createVoice).toHaveBeenCalledWith('Beta', 'chatterbox', file));
  });

  it('deletes a voice', async () => {
    render(<VoiceLibrary />);
    await waitFor(() => screen.getByText('Alpha'));
    await userEvent.click(screen.getByRole('button', { name: 'delete Alpha' }));
    await waitFor(() => expect(deleteVoice).toHaveBeenCalledWith('1'));
  });

  it('surfaces create errors', async () => {
    createVoice.mockRejectedValueOnce(new Error('clone failed'));
    render(<VoiceLibrary />);
    await userEvent.type(screen.getByLabelText('voice name'), 'X');
    await userEvent.click(screen.getByRole('button', { name: 'Create' }));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('clone failed'));
  });

  it('shows an empty state when there are no voices', async () => {
    listVoices.mockResolvedValue([]);
    render(<VoiceLibrary />);
    await waitFor(() => expect(screen.getByText('No voices yet.')).toBeInTheDocument());
  });
});
