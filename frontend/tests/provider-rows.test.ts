import { describe, expect, it } from 'vitest'
import { buildProviderRows } from '@/utils/providerRows'

describe('provider rows', () => {
  it('merges catalog and configured instances by id', () => {
    const rows = buildProviderRows(
      [{ type: 'exa', name: 'Exa', capabilities: ['search'], description_key: 'providers.desc.exa' }],
      [{ id: 'exa-work', type: 'exa', capabilities: ['search'], enabled: true, weight: 10, priority: 100 }],
      {}, {},
    )
    expect(rows[0].id).toBe('exa-work')
    expect(rows[0].type).toBe('exa')
    expect(rows[0].descriptionKey).toBe('providers.desc.exa')
  })

  it('keeps unconfigured catalog types addable', () => {
    const rows = buildProviderRows(
      [{ type: 'exa', name: 'Exa', capabilities: ['search'], description_key: 'providers.desc.exa' }],
      [], {}, {},
    )
    expect(rows).toHaveLength(1)
    expect(rows[0]).toMatchObject({
      type: 'exa',
      id: 'exa',
      name: 'Exa',
      descriptionKey: 'providers.desc.exa',
      capabilities: ['search'],
      configured: false,
      weight: null,
      priority: null,
      keyCount: 0,
    })
  })

  it('groups multiple instances of a type and adds no empty row for it', () => {
    const rows = buildProviderRows(
      [
        { type: 'exa', name: 'Exa', capabilities: ['search'], description_key: 'providers.desc.exa' },
        { type: 'ddg', name: 'DuckDuckGo', capabilities: ['search'], description_key: 'providers.desc.ddg' },
      ],
      [
        { id: 'exa-a', type: 'exa', capabilities: ['search'], enabled: true, weight: 10, priority: 100 },
        { id: 'exa-b', type: 'exa', capabilities: ['search', 'extract'], enabled: true, weight: 20, priority: 50 },
      ],
      { 'exa-b': 3 },
      { 'exa-a': { status: 'ok', test: null, tests: {} } },
    )
    expect(rows.map((r) => r.id)).toEqual(['exa-a', 'exa-b', 'ddg'])
    expect(rows.filter((r) => r.type === 'exa')).toHaveLength(2)
    expect(rows[1].keyCount).toBe(3)
    expect(rows[0].status?.status).toBe('ok')
    expect(rows[2].configured).toBe(false)
  })

  it('shows configured providers without a catalog entry', () => {
    const rows = buildProviderRows(
      [],
      [{ id: 'legacy', type: 'legacy', capabilities: ['search'], enabled: true, weight: 1, priority: 1 }],
      {}, {},
    )
    expect(rows[0]).toMatchObject({
      type: 'legacy',
      id: 'legacy',
      name: 'legacy',
      descriptionKey: '',
      configured: true,
    })
  })
})
