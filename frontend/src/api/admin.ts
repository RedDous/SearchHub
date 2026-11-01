import { request } from './client'

export interface KeyPoolCfg {
  max_concurrency: number
  rps_limit: number
  cooldown_s: number
}
export type CapabilityName = 'search' | 'extract'
export type AuthMode = 'none' | 'bearer' | 'header' | 'query'
export type FieldType = 'string' | 'text' | 'int' | 'float' | 'bool' | 'enum' | 'string_list' | 'secret'
export type KeyPoolParams = 'none' | 'rps' | 'full'

export interface AuthSpec {
  mode: AuthMode
  header_name: string | null
  query_param: string | null
  required: boolean
  optional: boolean
  key_prefix: string | null
  hint: string
}
export interface EndpointSpec {
  default: string | null
  overridable: boolean
  required: boolean
  label: string
  placeholder: string
}
export interface FieldSpec {
  key: string
  /** i18n key; translate in the view, not here. */
  label: string
  type: FieldType
  default?: unknown
  choices?: string[]
  required?: boolean
  capability?: CapabilityName | null
  group?: string
  /** i18n key; translate in the view, not here. */
  help?: string
  placeholder?: string
  min?: number | null
  max?: number | null
  step?: number | null
  advanced?: boolean
  visible_when?: Record<string, unknown> | null
}
export interface TestSpec {
  capability: CapabilityName
  query: string | null
  urls: string[]
  max_chars: number
  min_results: number
  expect_content: boolean
}

export interface ProviderCfg {
  id: string
  type: string
  capabilities: string[]
  enabled: boolean
  weight: number
  priority: number
  max_results: number
  base_url: string | null
  key_pool: KeyPoolCfg
  options: Record<string, unknown>
}
export interface ProviderType {
  type: string
  name: string
  capabilities: string[]
  key_pool_params: KeyPoolParams
  auth: AuthSpec
  endpoint: EndpointSpec
  fields: FieldSpec[]
  tests: TestSpec[]
  description_key?: string | null
  docs_url?: string | null
  requires_key: boolean
  optional_key: boolean
  requires_base_url: boolean
  key_prefix?: string | null
  show_max_results: boolean
  show_options: boolean
}
export interface TokenInfo {
  id: string
  name: string
  created_at: number
  revoked: boolean
  hash_prefix: string
}
export interface ProviderTest {
  success: boolean
  capability?: string
  count?: number
  took_ms?: number
  error?: string
  at: number
}

export type ProviderStatusKind = 'ok' | 'failed' | 'untested' | 'missing_key' | 'missing_base_url'

export interface ProviderStatus {
  status: ProviderStatusKind
  /** Latest test across capabilities (kept for compatibility). */
  test: ProviderTest | null
  tests: Record<string, ProviderTest>
}

export interface AppConfigView {
  config: {
    strategy: { default_mode: string; timeout_s: number }
    cache: { enabled: boolean; search_ttl_s: number; extract_ttl_s: number }
    history: { retention_days: number; redact_queries: boolean }
    providers: ProviderCfg[]
    auth: { tokens: Array<{ name: string; token_hash: string; id: string; created_at: number; revoked: boolean }> }
    admin: { username: string; session_ttl_hours: number }
  }
  config_version: number
  updated_at: number
  password_is_default: boolean
  version: string
  commit: string
  provider_status: Record<string, ProviderStatus>
}
export interface KeyEntry { index: number; masked: string; status: { key: string; cooling_until: number; in_flight: number; ok: boolean } | null }
export interface HistoryRow { id: number; ts: number; capability: string; query: string; params: string; providers: string; cache_hit: number; took_ms: number; result_count: number; success: number; error: string; token_name: string; response_preview: string; has_full: number }

export interface HistoryFullEntry {
  title?: string
  url: string
  description?: string
  content?: string
  provider?: string
  error?: string | null
}
export interface StatsSummary {
  total: number; success: number; cache_hits: number; avg_took_ms: number
  searches: number; extracts: number; success_rate: number; cache_hit_rate: number
  providers: Array<Record<string, unknown>>
}
export interface TimeseriesRow { ts: number; count: number; success: number; cache_hits: number; avg_took_ms: number }

export const adminApi = {
  login: (username: string, password: string) =>
    request<{ username: string }>('/api/admin/login', { method: 'POST', body: { username, password } }),
  logout: () => request<null>('/api/admin/logout', { method: 'POST' }),
  changePassword: (old_password: string, new_password: string) =>
    request<null>('/api/admin/change-password', { method: 'POST', body: { old_password, new_password } }),
  getConfig: () => request<AppConfigView>('/api/admin/config'),
  getProviderTypes: () => request<{ types: ProviderType[] }>('/api/admin/provider-types'),
  createProvider: (cfg: ProviderCfg) => request<null>('/api/admin/providers', { method: 'POST', body: cfg }),
  updateProvider: (id: string, cfg: ProviderCfg) =>
    request<null>(`/api/admin/providers/${id}`, { method: 'PUT', body: cfg }),
  deleteProvider: (id: string) => request<null>(`/api/admin/providers/${id}`, { method: 'DELETE' }),
  testProvider: (id: string) =>
    request<{ capability: string; count: number; took_ms: number }>(`/api/admin/providers/${id}/test`, { method: 'POST' }),
  testProviderConfig: (cfg: ProviderCfg) =>
    request<{ capability: string; count: number; took_ms: number }>('/api/admin/providers/test', { method: 'POST', body: cfg }),
  listKeys: (id: string) => request<{ keys: KeyEntry[] }>(`/api/admin/providers/${id}/keys`),
  addKey: (id: string, key: string) => request<null>(`/api/admin/providers/${id}/keys`, { method: 'POST', body: { key } }),
  deleteKey: (id: string, index: number) => request<null>(`/api/admin/providers/${id}/keys/${index}`, { method: 'DELETE' }),
  listTokens: () => request<{ tokens: TokenInfo[] }>('/api/admin/tokens'),
  createToken: (name: string) => request<{ id: string; name: string; token: string }>('/api/admin/tokens', { method: 'POST', body: { name } }),
  deleteToken: (id: string) => request<null>(`/api/admin/tokens/${id}`, { method: 'DELETE' }),
  updateToken: (id: string, name: string) =>
    request<null>(`/api/admin/tokens/${id}`, { method: 'PATCH', body: { name } }),
  updateSettings: (partial: Record<string, unknown>) =>
    request<{ config_version: number }>('/api/admin/settings', { method: 'PUT', body: partial }),
  listHistory: (params: Record<string, string | number | undefined>) =>
    request<{ rows: HistoryRow[] }>('/api/admin/history', { params }),
    getHistoryFull(id: number) {
      return request<{ response_full: string }>(`/api/admin/history/${id}/full`)
    },
  getStatsSummary: (hours = 24) => request<StatsSummary>('/api/admin/stats/summary', { params: { hours } }),
  getStatsTimeseries: (hours = 24) => request<{ rows: TimeseriesRow[] }>('/api/admin/stats/timeseries', { params: { hours } }),
}
