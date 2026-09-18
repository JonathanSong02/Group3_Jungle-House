import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Keep localhost API requests on the same browser origin during development.
// Vite forwards /api/* to the existing local Flask server without changing paths.
// This preserves Flask session cookies and CSRF protection.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
      },
      // Local SOP images and uploaded files need the same-origin proxy too.
      // Keep the path unchanged so Flask's /static routes handle auth and files.
      '/static': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
      },
    },
  },
});
