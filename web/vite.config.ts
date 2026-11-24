/// <reference types="vitest/config" />
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const contractsDir = fileURLToPath(new URL('../contracts', import.meta.url))

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@contracts': contractsDir },
  },
  server: {
    // The dev server serves files from ../contracts through the alias.
    fs: { allow: ['.', contractsDir] },
  },
  test: {
    environment: 'node',
    include: ['src/**/*.test.{ts,tsx}'],
  },
})
