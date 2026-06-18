import '@testing-library/jest-dom/vitest';
import { afterEach, vi } from 'vitest';
import { cleanup } from '@testing-library/react';

// Reset DOM and mocks between tests, and provide a stable object-URL stub so
// components that create audio URLs work under jsdom.
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  localStorage.clear();
});

if (!('createObjectURL' in URL)) {
  // @ts-expect-error jsdom lacks createObjectURL
  URL.createObjectURL = () => 'blob:mock';
}
URL.createObjectURL = vi.fn(() => 'blob:mock');
