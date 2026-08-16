import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import type { Plugin } from 'vite'

// vitest's module runner executes modules as native ESM where imported
// bindings are read-only, but the api client exposes a reassignable
// `onUnauthorized` hook that tests override by assigning the imported name.
// In SSR (vitest) only, redefine that export on the module exports object
// with a setter so such assignments mutate the live binding.
function writableUnauthorizedHook(): Plugin {
  return {
    name: 'searchhub:writable-unauthorized-hook',
    enforce: 'post',
    transform(code, id) {
      if (!id.endsWith('/src/api/client.ts')) return null
      const inject =
        `\nif (typeof __vite_ssr_exports__ !== 'undefined') ` +
        `Object.defineProperty(__vite_ssr_exports__, 'onUnauthorized', ` +
        `{ configurable: true, enumerable: true, get: () => onUnauthorized, set: (v) => { onUnauthorized = v } })\n`
      return code + inject
    },
  }
}

export default defineConfig({
  plugins: [vue(), writableUnauthorizedHook()],
  resolve: { alias: { '@': new URL('./src', import.meta.url).pathname } },
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8000',
      '/v1': 'http://127.0.0.1:8000',
      '/healthz': 'http://127.0.0.1:8000',
    },
  },
  test: {
    environment: 'jsdom',
  },
})
