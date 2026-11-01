import { defineStore } from 'pinia'
import { adminApi, type ProviderType } from '@/api/admin'

const CAPABILITIES = ['search', 'extract']
const FIELD_TYPES = ['string', 'text', 'int', 'float', 'bool', 'enum', 'string_list', 'secret']
const AUTH_MODES = ['none', 'bearer', 'header', 'query']
const KEY_POOL_PARAMS = ['none', 'rps', 'full']

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v)
}

function isCapability(v: unknown): boolean {
  return typeof v === 'string' && CAPABILITIES.includes(v)
}

function isBoolean(v: unknown): boolean {
  return typeof v === 'boolean'
}

function isStringOrNull(v: unknown): boolean {
  return v === null || typeof v === 'string'
}

function isNumberOrNull(v: unknown): boolean {
  return v === null || (typeof v === 'number' && Number.isFinite(v))
}

function isStringArray(v: unknown): boolean {
  return Array.isArray(v) && v.every((x) => typeof x === 'string')
}

function isAuthSpec(v: unknown): boolean {
  if (!isRecord(v)) return false
  return typeof v.mode === 'string' && AUTH_MODES.includes(v.mode) &&
    isStringOrNull(v.header_name) &&
    isStringOrNull(v.query_param) &&
    isBoolean(v.required) &&
    isBoolean(v.optional) &&
    isStringOrNull(v.key_prefix) &&
    typeof v.hint === 'string'
}

function isEndpointSpec(v: unknown): boolean {
  if (!isRecord(v)) return false
  return isStringOrNull(v.default) &&
    isBoolean(v.overridable) &&
    isBoolean(v.required) &&
    typeof v.label === 'string' &&
    typeof v.placeholder === 'string'
}

function isFieldSpec(v: unknown): boolean {
  if (!isRecord(v)) return false
  return typeof v.key === 'string' && v.key.length > 0 &&
    typeof v.label === 'string' &&
    typeof v.type === 'string' && FIELD_TYPES.includes(v.type) &&
    (v.choices === undefined || isStringArray(v.choices)) &&
    (v.required === undefined || isBoolean(v.required)) &&
    (v.capability === null || v.capability === undefined || isCapability(v.capability)) &&
    (v.group === undefined || typeof v.group === 'string') &&
    (v.help === undefined || typeof v.help === 'string') &&
    (v.placeholder === undefined || typeof v.placeholder === 'string') &&
    (v.min === undefined || isNumberOrNull(v.min)) &&
    (v.max === undefined || isNumberOrNull(v.max)) &&
    (v.step === undefined || isNumberOrNull(v.step)) &&
    (v.advanced === undefined || isBoolean(v.advanced)) &&
    (v.visible_when === undefined || v.visible_when === null || isRecord(v.visible_when))
}

function isTestSpec(v: unknown): boolean {
  if (!isRecord(v)) return false
  return isCapability(v.capability) &&
    isStringOrNull(v.query) &&
    isStringArray(v.urls) &&
    typeof v.max_chars === 'number' && Number.isFinite(v.max_chars) &&
    typeof v.min_results === 'number' && Number.isFinite(v.min_results) &&
    isBoolean(v.expect_content)
}

export function normalizeProviderTypes(raw: unknown): ProviderType[] {
  if (!Array.isArray(raw)) return []
  return raw.filter((t): t is ProviderType => {
    if (!isRecord(t)) return false
    return typeof t.type === 'string' && t.type.length > 0 &&
      typeof t.name === 'string' &&
      Array.isArray(t.capabilities) &&
      t.capabilities.every(isCapability) &&
      KEY_POOL_PARAMS.includes(String(t.key_pool_params)) &&
      isAuthSpec(t.auth) &&
      isEndpointSpec(t.endpoint) &&
      Array.isArray(t.fields) && t.fields.every(isFieldSpec) &&
      Array.isArray(t.tests) && t.tests.every(isTestSpec) &&
      (typeof t.optional_key === 'boolean' || t.optional_key === undefined)
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
