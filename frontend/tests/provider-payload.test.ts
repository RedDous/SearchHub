import { describe, expect, it } from 'vitest'
import { buildProviderPayload, defaultOptions } from '@/utils/providerPayload'

describe('provider payload', () => {
  it('includes type, id, and options', () => {
    const payload = buildProviderPayload({
      id: 'exa-work', type: 'exa', capabilities: ['search'],
      enabled: true, weight: 10, priority: 100, max_results: 8,
      base_url: '', key_pool: { max_concurrency: 2, rps_limit: 10, cooldown_s: 60 },
      options: { search_type: 'deep' },
    })
    expect(payload.type).toBe('exa')
    expect(payload.id).toBe('exa-work')
    expect(payload.options.search_type).toBe('deep')
  })

  it('builds defaults from field specs', () => {
    expect(defaultOptions([
      { key: 'search_type', label: 'x', type: 'enum', default: 'auto' },
    ])).toEqual({ search_type: 'auto' })
  })

  it('trims the id and normalizes an empty base_url to null', () => {
    const payload = buildProviderPayload({
      id: '  exa-work  ', type: 'exa', capabilities: ['search'],
      enabled: true, weight: 10, priority: 100, max_results: 8,
      base_url: '  ', key_pool: { max_concurrency: 2, rps_limit: 10, cooldown_s: 60 },
      options: {},
    })
    expect(payload.id).toBe('exa-work')
    expect(payload.base_url).toBeNull()
  })

  it('keeps a configured base_url', () => {
    const payload = buildProviderPayload({
      id: 'searxng', type: 'searxng', capabilities: ['search'],
      enabled: true, weight: 10, priority: 100, max_results: 8,
      base_url: ' http://searxng:8080 ', key_pool: { max_concurrency: 2, rps_limit: 10, cooldown_s: 60 },
      options: {},
    })
    expect(payload.base_url).toBe('http://searxng:8080')
  })
})
