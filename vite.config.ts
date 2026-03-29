import { defineConfig } from 'vite';

const REPO_BASE = '/poncho/';

export default defineConfig(({ command }) => ({
  base: command === 'serve' ? '/' : REPO_BASE,
  root: '.',
  publicDir: 'public',
  server: {
    open: true,
  },
  build: {
    outDir: 'dist',
  },
}));
