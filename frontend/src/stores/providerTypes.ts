import { defineStore } from 'pinia'
import { adminApi, type ProviderType } from '@/api/admin'

export function normalizeProviderTypes(raw: unknown): ProviderType[] {
  if (!Array.isArray(raw)) return []
  return raw.filter((t): t is ProviderType => {
    if (typeof t !== 'object' || t === null) return false
    const x = t as Record<string, unknown>
    return typeof x.type === 'string' && x.type.length > 0 &&
      typeof x.name === 'string' &&
      Array.isArray(x.capabilities) &&
      x.capabilities.every((c) => c === 'search' || c === 'extract') &&
      ['none', 'rps', 'full'].includes(String(x.key_pool_params)) &&
      typeof x.optional_key === 'boolean'
  })
}

export const useProviderTypesStore = defineStore('providerTypes', {
  state: () => ({ types: [] as ProviderType[], loaded: false, error: '' }),
  getters: {
    byType: (state) => (type: string) => state.types.find((t) => t.type === type),
  },
  actions: {
    async load(): Promise<void> {
      if (this.loaded) return
      try {
        const r = await adminApi.getProviderTypes()
        this.types = normalizeProviderTypes(r.types)
        this.loaded = true
      } catch (e) {
        this.error = e instanceof Error ? e.message : String(e)
      }
    },
  },
})