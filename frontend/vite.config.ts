import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [
    react(),
    // In Vite dev, `public/` is served at root (e.g. /foo.json), NOT at /public/foo.json.
    // Vercel production (outputDirectory:".") serves the directory tree as-is, so
    // /public/foo.json works there. This middleware maps /public/* → /* in dev so
    // both environments behave the same without changing fetch() URLs in index.html.
    {
      name: 'public-prefix-compat',
      configureServer(server) {
        server.middlewares.use((req, _res, next) => {
          if (req.url?.startsWith('/public/')) req.url = req.url.slice(7) || '/';
          next();
        });
      },
    },
  ],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/health': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
});
