// Construye los bancos de pruebas de interfaz: teclado de modales (harness.jsx,
// T7.2), estados de datos remotos (states.jsx, T7.3) y el panel de
// explicabilidad (explain.jsx, T9.2). No entran en ninguno de los dos builds de
// la aplicación.
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  root: path.resolve(__dirname),
  base: './',
  plugins: [react()],
  build: {
    outDir: path.resolve(__dirname, 'dist'),
    emptyOutDir: true,
    rollupOptions: {
      input: {
        modales: path.resolve(__dirname, 'index.html'),
        estados: path.resolve(__dirname, 'states.html'),
        explicabilidad: path.resolve(__dirname, 'explain.html'),
        idioma: path.resolve(__dirname, 'language.html'),
      },
    },
  },
});
