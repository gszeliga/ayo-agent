/// <reference types="vitest/config" />
import { readFileSync } from 'node:fs'
import { fileURLToPath, URL } from 'node:url'

import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

import { apiPrefixes, proxyPattern } from './src/apiPaths'

// The API's paths go to the local API, so the UI and the API share one origin (no CORS),
// as behind Caddy in production. The prefixes come from the committed contract.
const API_TARGET = 'http://127.0.0.1:8000'
const contract = JSON.parse(
  readFileSync(new URL('../docs/openapi.json', import.meta.url), 'utf8'),
) as { paths: Record<string, unknown> }
const apiProxy = Object.fromEntries(
  apiPrefixes(Object.keys(contract.paths)).map((prefix) => [proxyPattern(prefix), API_TARGET]),
)

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  // Local only unless started with `--host` (ui/README.md, "From another device").
  server: { port: 5173, strictPort: true, proxy: apiProxy },
  preview: { port: 4173, strictPort: true, proxy: apiProxy },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: false,
  },
})
