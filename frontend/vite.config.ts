import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

const BACKEND = 'http://127.0.0.1:8742';

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy: { '/api': BACKEND },
  },
  build: { outDir: 'dist', chunkSizeWarningLimit: 6000 },
  test: { include: ['src/**/*.test.ts'], environment: 'node' },
});
