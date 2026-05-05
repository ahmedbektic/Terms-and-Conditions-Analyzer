import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import { sentryVitePlugin } from '@sentry/vite-plugin';

import { cloudflare } from "@cloudflare/vite-plugin";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const plugins = [react()];
  const sentryAuthToken = env.SENTRY_AUTH_TOKEN?.trim();
  const sentryOrg = env.SENTRY_ORG?.trim();
  const sentryProject = env.SENTRY_PROJECT?.trim();
  const sentryRelease = env.VITE_SENTRY_RELEASE?.trim();

  // Vitest runs against browser/jsdom units; it does not need the Cloudflare
  // worker environment bootstrapped the way deploy/preview builds do.
  if (!process.env.VITEST) {
    plugins.push(cloudflare());
  }

  if (sentryAuthToken && sentryOrg && sentryProject && sentryRelease) {
    plugins.push(
      sentryVitePlugin({
        authToken: sentryAuthToken,
        org: sentryOrg,
        project: sentryProject,
        release: {
          name: sentryRelease,
        },
        sourcemaps: {
          assets: ['./dist/client/assets/**'],
        },
        telemetry: false,
      }),
    );
  }

  return {
    plugins,
    base: '/',
    test: {
      setupFiles: ['./tests/vitest-setup.ts'],
    },
    build: {
      outDir: 'dist',
      emptyOutDir: true,
      sourcemap: 'hidden',
    },
    preview: {
      port: 4173,
    },
  };
});
