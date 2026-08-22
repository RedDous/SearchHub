export interface ProviderCatalogEntry {
  type: string
  name: string
  descKey: string
  capabilities: string[]
  requiresKey: boolean
  requiresBaseUrl: boolean
}

export const PROVIDER_CATALOG: ProviderCatalogEntry[] = [
  { type: 'exa', name: 'Exa', descKey: 'providers.desc.exa', capabilities: ['search', 'extract'], requiresKey: true, requiresBaseUrl: false },
  { type: 'tavily', name: 'Tavily', descKey: 'providers.desc.tavily', capabilities: ['search', 'extract'], requiresKey: true, requiresBaseUrl: false },
  { type: 'ddg', name: 'DuckDuckGo', descKey: 'providers.desc.ddg', capabilities: ['search'], requiresKey: false, requiresBaseUrl: false },
  { type: 'searxng', name: 'SearXNG', descKey: 'providers.desc.searxng', capabilities: ['search'], requiresKey: false, requiresBaseUrl: true },
  { type: 'jina', name: 'Jina Reader', descKey: 'providers.desc.jina', capabilities: ['extract'], requiresKey: false, requiresBaseUrl: false },
  { type: 'trafilatura', name: 'Trafilatura', descKey: 'providers.desc.trafilatura', capabilities: ['extract'], requiresKey: false, requiresBaseUrl: false },
]

export function catalogEntry(type: string): ProviderCatalogEntry | undefined {
  return PROVIDER_CATALOG.find((e) => e.type === type)
}