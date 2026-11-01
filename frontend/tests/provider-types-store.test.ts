import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { normalizeProviderTypes, useProviderTypesStore } from '@/stores/providerTypes'

const auth = {
  mode: 'none', header_name: null, query_param: null,
  required: false, optional: false, key_prefix: null, hint: '',
}
const endpoint = {
  default: null, overridable: false, required: false, label: 'Base URL', placeholder: '',
}
const field = {
  key: 'region', label: 'providers.fields.ddg.region', type: 'string',
  default: null, choices: [], required: false, capability: 'search', group: 'search',
  help: '', placeholder: '', min: null, max: null, step: null, advanced: false,
  visible_when: null,
}
const test = {
  capability: 'search', query: 'q', urls: [], max_chars: 200,
  min_results: 0, expect_content: false,
}

function typeEntry(overrides: Record<string, unknown> = {}) {
  return {
    type: 'exa', name: 'Exa', capabilities: ['search', 'extract'],
    key_pool_params: 'full', optional_key: false,
    auth, endpoint, fields: [field], tests: [test],
    ...overrides,
  }
}

describe('normalizeProviderTypes', () => {
  it('filters malformed entries', () => {
    const raw = [
      typeEntry(),
      typeEntry({ type: 'bad', name: '', capabilities: ['crawl'], key_pool_params: 'weird' }),
      null,
      'nope',
    ]
    const types = normalizeProviderTypes(raw)
    expect(types).toHaveLength(1)
    expect(types[0].type).toBe('exa')
    expect(types[0].auth.mode).toBe('none')
    expect(types[0].fields[0].key).toBe('region')
    expect(types[0].tests[0].capability).toBe('search')
  })

  it('rejects entries missing the new schema fields', () => {
    const raw = [
      typeEntry({ auth: undefined }),
      typeEntry({ endpoint: undefined }),
      typeEntry({ fields: undefined }),
      typeEntry({ tests: undefined }),
      typeEntry({ fields: 'nope' }),
      typeEntry({ auth: { mode: 'weird' } }),
      typeEntry({ tests: [{ capability: 'crawl' }] }),
    ]
    expect(normalizeProviderTypes(raw)).toHaveLength(0)
  })
})

describe('provider types store', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('loads once and caches', async () => {
    const store = useProviderTypesStore()
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ success: true, data: { types: [
        {
          type: 'ddg', name: 'DuckDuckGo', capabilities: ['search'],
          key_pool_params: 'none', optional_key: false,
          auth, endpoint, fields: [field], tests: [test],
        },
      ] } }), { status: 200 }),
    )
    await store.load()
    await store.load()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(store.types[0].type).toBe('ddg')
    expect(store.byType('ddg')?.name).toBe('DuckDuckGo')
  })
})
