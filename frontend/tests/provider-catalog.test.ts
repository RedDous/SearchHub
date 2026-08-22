import { describe, expect, it } from 'vitest'
import { PROVIDER_CATALOG, catalogEntry } from '@/api/providerCatalog'

describe('provider catalog', () => {
  it('covers all six supported providers with unique types', () => {
    const types = PROVIDER_CATALOG.map((e) => e.type)
    expect(types).toEqual(['exa', 'tavily', 'ddg', 'searxng', 'jina', 'trafilatura'])
    expect(new Set(types).size).toBe(types.length)
  })

  it('has non-empty names and desc keys', () => {
    for (const e of PROVIDER_CATALOG) {
      expect(e.name.length).toBeGreaterThan(0)
      expect(e.descKey.startsWith('providers.desc.')).toBe(true)
    }
  })

  it('exa and tavily require keys; searxng requires base url', () => {
    expect(catalogEntry('exa')?.requiresKey).toBe(true)
    expect(catalogEntry('tavily')?.requiresKey).toBe(true)
    expect(catalogEntry('searxng')?.requiresBaseUrl).toBe(true)
    expect(catalogEntry('ddg')?.requiresKey).toBe(false)
  })

  it('capabilities are valid subsets', () => {
    for (const e of PROVIDER_CATALOG) {
      for (const c of e.capabilities) {
        expect(['search', 'extract']).toContain(c)
      }
    }
  })

  it('returns undefined for unknown type', () => {
    expect(catalogEntry('nope')).toBeUndefined()
  })
})