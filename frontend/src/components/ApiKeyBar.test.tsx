import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ApiKeyBar } from './ApiKeyBar';

describe('ApiKeyBar', () => {
  it('saves the key and shows confirmation', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    render(<ApiKeyBar />);
    const input = screen.getByLabelText('API key');
    await userEvent.type(input, 'sk-hearsay-abc');
    await userEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(localStorage.getItem('hearsay.apiKey')).toBe('sk-hearsay-abc');
    expect(screen.getByRole('status')).toHaveTextContent('Saved');
    vi.useRealTimers();
  });
});
