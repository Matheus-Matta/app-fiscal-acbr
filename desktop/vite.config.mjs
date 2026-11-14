import { fileURLToPath } from 'node:url';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// No pacote, a página só fala com o processo principal (IPC): nada de rede, nada de
// script de fora. No `npm run dev` a CSP fica de fora, porque o Vite injeta script em linha.
const CSP =
  "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; " +
  "connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'";

const csp = () => ({
  name: 'csp',
  transformIndexHtml: {
    order: 'post',
    handler: (html, contexto) =>
      contexto.server
        ? html
        : html.replace('<head>', `<head>\n    <meta http-equiv="Content-Security-Policy" content="${CSP}" />`),
  },
});

export default defineConfig({
  root: fileURLToPath(new URL('./src/renderer', import.meta.url)),
  base: './',
  plugins: [react(), csp()],
  server: { port: 5173, strictPort: true },
  build: {
    outDir: fileURLToPath(new URL('./build', import.meta.url)),
    emptyOutDir: true,
  },
});
