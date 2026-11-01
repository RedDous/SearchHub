import type { KeyPoolCfg, ProviderCfg } from '@/api/admin'
import { defaultOptions } from '@/utils/providerFields'

export { defaultOptions }

/** The subset of the detail form that maps directly onto `ProviderCfg`. */
export interface ProviderPayloadInput {
  id: string
  type: string
  capabilities: string[]
  enabled: boolean
  weight: number
  priority: number
  max_results: number
  base_url: string
  key_pool: KeyPoolCfg
  options: Record<string, unknown>
}

/**
 * Build the admin API payload from the form model.
 *
 * The id is trimmed and a blank `base_url` is normalized to `null` so the
 * backend sees "not configured" rather than an empty string. Arrays and the
 * options object are copied so later form edits cannot mutate a request body
 * that is still in flight.
 */
export function buildProviderPayload(input: ProviderPayloadInput): ProviderCfg {
  return {
    id: input.id.trim(),
    type: input.type,
    capabilities: [...input.capabilities],
    enabled: input.enabled,
    weight: input.weight,
    priority: input.priority,
    max_results: input.max_results,
    base_url: input.base_url.trim() || null,
    key_pool: { ...input.key_pool },
    options: { ...input.options },
  }
}
