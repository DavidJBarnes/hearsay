/// <reference types="vitest" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Vite + Vitest configuration. The dev server proxies API calls to the gateway
// so the console can run on a separate port during development.
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      '/v1': { target: 'http://localhost:8000', changeOrigin: true, ws: true },
      '/metrics': 'http://localhost:8000',
      '/healthz': 'http://localhost:8000',
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    css: false,
  },
});
