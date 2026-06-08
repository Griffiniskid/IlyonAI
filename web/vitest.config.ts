import { defineConfig, configDefaults } from 'vitest/config'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./tests/setup.ts'],
    // *.cjs are plain Node assertion scripts (next.config rewrites + route.ts source
    // checks) that run via `npm run test:node`, not under jsdom/vitest. vitest's
    // default include picks up *.test.cjs and reports "No test suite found" — exclude them.
    exclude: [...configDefaults.exclude, '**/*.cjs'],
    alias: {
      '@': path.resolve(__dirname, './')
    }
  }
})
