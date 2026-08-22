import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { normalizeProviderTypes, useProviderTypesStore } from '@/stores/providerTypes'

describe('normalizeProviderTypes', () => {
  it('filters malformed entries', () => {
    const raw = [
      { type: 'exa', name: 'Exa', capabilities: ['search', 'extract'], key_pool_params: 'full', optional_key: false },
      { type: 'bad', name: '', capabilities: ['crawl'], key_pool_params: 'weird' },
      null,
      'nope',
    ]
    const types = normalizeProviderTypes(raw)
    expect(types).toHaveLength(1)
    expect(types[0].type).toBe('exa')
  })
})

describe('provider types store', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('loads once and caches', async () => {
    const store = useProviderTypesStore()
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ success: true, data: { types: [
        { type: 'ddg', name: 'DuckDuckGo', capabilities: ['search'], key_pool_params: 'none', optional_key: false },
      ] } }), { status: 200 }),
    )
    await store.load()
    await store.load()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(store.types[0].type).toBe('ddg')
    expect(store.byType('ddg')?.name).toBe('DuckDuckGo')
  })
})