import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    // The Python API (server/) runs on 8000; the app calls it at /api.
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
});
