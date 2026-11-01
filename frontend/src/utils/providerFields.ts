import type { CapabilityName, FieldSpec, ProviderType } from '@/api/admin'

/** Group fields by `group`, optionally restricted to one capability. */
export function groupFields(
  fields: readonly FieldSpec[],
  capability?: CapabilityName,
): Record<string, FieldSpec[]> {
  const out: Record<string, FieldSpec[]> = {}
  for (const field of fields) {
    if (capability && field.capability && field.capability !== capability) continue
    const group = field.group || 'general'
    ;(out[group] ??= []).push(field)
  }
  return out
}

/** A field is visible when every `visible_when` entry matches the current values. */
export function isFieldVisible(
  field: FieldSpec,
  values: Record<string, unknown>,
): boolean {
  const conditions = field.visible_when
  if (!conditions) return true
  return Object.entries(conditions).every(([key, expected]) => values[key] === expected)
}

/** Effective default for a field; arrays are copied so callers cannot mutate specs. */
export function defaultFieldValue(field: FieldSpec): unknown {
  const value = field.default
  if (Array.isArray(value)) return [...value]
  return value ?? null
}

/** Options object containing every field's default value. */
export function defaultOptions(fields: readonly FieldSpec[]): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const field of fields) out[field.key] = defaultFieldValue(field)
  return out
}

/**
 * Whether to render the rate-limit / key-pool card. Providers with auth need
 * it for key management; providers without auth may still have a rate limit.
 */
export function shouldShowKeyPool(entry: ProviderType | undefined): boolean {
  if (!entry) return false
  return entry.auth.required || entry.auth.optional || entry.key_pool_params !== 'none'
}

/** Whether to render key rows and add controls; only providers with auth accept keys. */
export function shouldShowKeyRows(entry: ProviderType | undefined): boolean {
  if (!entry) return false
  return entry.auth.required || entry.auth.optional
}
