import type { ProviderCfg, ProviderStatus, ProviderType } from '@/api/admin'

/** Catalog metadata needed to render a provider row. */
export type ProviderCatalogEntry = Pick<ProviderType, 'type' | 'name' | 'capabilities'> & {
  description_key?: string | null
}

/** Configured instance data needed to render a provider row. */
export type ProviderInstance = Pick<
  ProviderCfg,
  'id' | 'type' | 'capabilities' | 'weight' | 'priority'
> &
  Partial<ProviderCfg>

export interface ProviderRow {
  /** Catalog type, used for metadata and the "add" route. */
  type: string
  /** Instance id, used for detail routes and delete actions. */
  id: string
  /** Catalog display name (falls back to the instance id). */
  name: string
  /** i18n key for the catalog description, or an empty string. */
  descriptionKey: string
  capabilities: string[]
  configured: boolean
  weight: number | null
  priority: number | null
  keyCount: number
  status?: ProviderStatus
}

function configuredRow(
  instance: ProviderInstance,
  entry: ProviderCatalogEntry | undefined,
  keyCounts: Record<string, number>,
  status: Record<string, ProviderStatus>,
): ProviderRow {
  const capabilities = instance.capabilities?.length ? instance.capabilities : entry?.capabilities ?? []
  return {
    type: entry?.type || instance.type || instance.id,
    id: instance.id,
    name: entry?.name || instance.id,
    descriptionKey: entry?.description_key ?? '',
    capabilities: [...capabilities],
    configured: true,
    weight: instance.weight,
    priority: instance.priority,
    keyCount: keyCounts[instance.id] ?? 0,
    status: status[instance.id],
  }
}

function unconfiguredRow(entry: ProviderCatalogEntry): ProviderRow {
  return {
    type: entry.type,
    id: entry.type,
    name: entry.name,
    descriptionKey: entry.description_key ?? '',
    capabilities: [...entry.capabilities],
    configured: false,
    weight: null,
    priority: null,
    keyCount: 0,
  }
}

/**
 * Merge the provider catalog with configured instances.
 *
 * v1 uses one instance per type, but the backend supports several. Rows are
 * emitted in catalog order; every instance of a type is kept together under
 * that type's metadata. A catalog type gets an unconfigured row (and therefore
 * an "add" action) only when it has no configured instance.
 */
export function buildProviderRows(
  types: ProviderCatalogEntry[],
  providers: ProviderInstance[],
  keyCounts: Record<string, number> = {},
  status: Record<string, ProviderStatus> = {},
): ProviderRow[] {
  const instancesByType = new Map<string, ProviderInstance[]>()
  for (const provider of providers) {
    const type = provider.type || provider.id
    const instances = instancesByType.get(type)
    if (instances) instances.push(provider)
    else instancesByType.set(type, [provider])
  }

  const rows: ProviderRow[] = []
  const catalogTypes = new Set<string>()

  for (const entry of types) {
    catalogTypes.add(entry.type)
    const instances = instancesByType.get(entry.type) ?? []
    if (instances.length === 0) {
      rows.push(unconfiguredRow(entry))
      continue
    }
    for (const instance of instances) {
      rows.push(configuredRow(instance, entry, keyCounts, status))
    }
  }

  for (const [type, instances] of instancesByType) {
    if (catalogTypes.has(type)) continue
    for (const instance of instances) {
      rows.push(configuredRow(instance, undefined, keyCounts, status))
    }
  }

  return rows
}
