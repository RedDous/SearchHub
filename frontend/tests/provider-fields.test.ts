import { describe, expect, it } from 'vitest'
import {
  defaultFieldValue,
  defaultOptions,
  groupFields,
  isFieldVisible,
  shouldShowKeyPool,
  shouldShowKeyRows,
} from '@/utils/providerFields'

const fields = [
  { key: 'search_type', label: 'x', type: 'enum' as const, choices: ['auto', 'deep'], default: 'auto', capability: 'search' as const, group: 'search' },
  { key: 'timeout_s', label: 'y', type: 'int' as const, default: null, capability: 'extract' as const, group: 'advanced' },
]

describe('provider fields', () => {
  it('groups by group and capability', () => {
    expect(groupFields(fields, 'search')).toEqual({ search: [fields[0]] })
  })

  it('groups all fields when no capability is given', () => {
    expect(groupFields(fields)).toEqual({
      search: [fields[0]],
      advanced: [fields[1]],
    })
  })

  it('honors visible_when', () => {
    expect(isFieldVisible({ ...fields[0], visible_when: { search_type: 'deep' } }, { search_type: 'auto' })).toBe(false)
  })

  it('shows fields whose conditions all match', () => {
    const field = { ...fields[0], visible_when: { search_type: 'deep', mode: 'x' } }
    expect(isFieldVisible(field, { search_type: 'deep', mode: 'x' })).toBe(true)
    expect(isFieldVisible(field, { search_type: 'deep' })).toBe(false)
  })

  it('shows fields without visible_when', () => {
    expect(isFieldVisible(fields[0], {})).toBe(true)
  })

  it('returns defaults', () => {
    expect(defaultFieldValue(fields[0])).toBe('auto')
    expect(defaultFieldValue(fields[1])).toBeNull()
  })

  it('builds default options from every field', () => {
    expect(defaultOptions(fields)).toEqual({ search_type: 'auto', timeout_s: null })
  })
})

const rpsOnly = {
  type: 'searxng', name: 'SearXNG', capabilities: ['search'],
  auth: { mode: 'none', header_name: null, query_param: null, required: false, optional: false, key_prefix: null, hint: '' },
  endpoint: { default: null, overridable: true, required: true, label: 'Base URL', placeholder: '' },
  fields: [], tests: [], key_pool_params: 'rps',
} as const

const keyed = {
  ...rpsOnly,
  type: 'exa', name: 'Exa',
  auth: { ...rpsOnly.auth, mode: 'header', header_name: 'x-api-key', required: true },
  key_pool_params: 'full',
} as const

describe('key pool visibility', () => {
  it('shows rate limits for RPS-only providers without key rows', () => {
    expect(shouldShowKeyPool(rpsOnly)).toBe(true)
    expect(shouldShowKeyRows(rpsOnly)).toBe(false)
  })
  it('shows key rows for keyed providers', () => {
    expect(shouldShowKeyPool(keyed)).toBe(true)
    expect(shouldShowKeyRows(keyed)).toBe(true)
  })
})
