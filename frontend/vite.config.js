import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig({
    plugins: [react()],
    build: {
        rolldownOptions: {
            output: {
                codeSplitting: {
                    groups: [
                        { name: 'react', test: /node_modules[\\/](react|react-dom)[\\/]/, priority: 3 },
                        { name: 'map', test: /node_modules[\\/](leaflet|react-leaflet|leaflet-velocity)[\\/]/, priority: 2 },
                        { name: 'icons', test: /node_modules[\\/]lucide-react[\\/]/, priority: 1 },
                    ],
                },
            },
        },
    },
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
