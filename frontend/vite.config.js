import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

import { cloudflare } from "@cloudflare/vite-plugin";

export default defineConfig(() => {
  const plugins = [react()];

  // Vitest runs against browser/jsdom units; it does not need the Cloudflare
  // worker environment bootstrapped the way deploy/preview builds do.
  if (!process.env.VITEST) {
    plugins.push(cloudflare());
  }

  return {
    plugins,
    base: '/',
    build: {
      outDir: 'dist',
      emptyOutDir: true,
    },
    preview: {
      port: 4173,
    },
  };
});
