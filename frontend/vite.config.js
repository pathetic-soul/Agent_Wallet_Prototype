import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./tests/setup.js'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html', 'json-summary'],
      include: ['src/services/api.js', 'src/context/AppStatusContext.jsx', 'src/hooks/usePendingRequests.js', 'src/lib/format.js', 'src/context/WalletDataContext.jsx'],
      thresholds: {
        lines: 90,
        functions: 90,
        statements: 90,
        branches: 80,
      },
    },
  },
});
