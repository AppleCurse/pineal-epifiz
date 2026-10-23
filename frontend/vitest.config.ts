import { defineConfig } from 'vitest/config';
import { svelte } from '@sveltejs/vite-plugin-svelte';
import { fileURLToPath } from 'url';
import path from 'path';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Sözleşme testleri GERÇEK bileşeni monte eder; ayrı bir yapılandırma
// `vite build`'i (üretim paketini) hiç etkilemez.
export default defineConfig({
  root: __dirname,
  plugins: [svelte({ hot: false })],
  resolve: {
    // Svelte 5: tarayıcı koşulu olmadan mount sırasında yanlış çözümleme olur.
    conditions: ['browser'],
  },
  test: {
    globals: true,
    environment: 'jsdom',
    include: ['src/**/*.test.ts'],
    setupFiles: ['./src/test-setup.ts'],
    restoreMocks: true,
  },
});
