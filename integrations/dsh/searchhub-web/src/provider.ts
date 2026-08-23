import { WebError } from '@deepseek-ai/dsh-web'
import type {
  WebFetchProvider, WebFetchRequest, WebFetchResult,
  WebSearchProvider, WebSearchRequest, WebSearchResult, WebSearchSource,
} from '@deepseek-ai/dsh-web'

export interface SearchHubProviderOptions {
  /** SearchHub REST base URL (no trailing slash). */
  baseURL: string
  /** Literal token; wins over resolveToken when present. */
  token?: string
  /** Resolve the current token for one operation. */
  resolveToken?: () => Promise<string | undefined>
}

async function requireToken(options: SearchHubProviderOptions): Promise<string> {
  const literal = options.token
  if (literal !== undefined && literal.length > 0) return literal
  if (options.resolveToken !== undefined) {
    const resolved = await options.resolveToken()
    if (resolved !== undefined && resolved.length > 0) return resolved
  }
  throw new WebError('SearchHub token is not configured', 'WEB_PROVIDER_ERROR')
}

export function isAvailable(options: SearchHubProviderOptions): boolean {
  return URL.canParse(options.baseURL)
    && ((options.token?.length ?? 0) > 0 || options.resolveToken !== undefined)
}

function mapSource(item: { title?: string; url?: string; description?: string; published_at?: string | null }): WebSearchSource | undefined {
  if (!item.url || item.url.length === 0) return undefined
  return {
    url: item.url,
    ...(item.title && item.title.length > 0 ? { title: item.title } : {}),
    ...(item.description && item.description.length > 0 ? { snippet: item.description } : {}),
    ...(item.published_at && item.published_at.length > 0 ? { publishedAt: item.published_at } : {}),
  }
}

export class SearchHubSearchProvider implements WebSearchProvider {
  readonly id = 'searchhub'

  constructor(private readonly resolveOptions: () => SearchHubProviderOptions) {}

  available(): boolean {
    return isAvailable(this.resolveOptions())
  }

  async search(request: WebSearchRequest, signal?: AbortSignal): Promise<WebSearchResult> {
    const options = this.resolveOptions()
    const token = await requireToken(options)
    const limit = request.maxResults ?? 5
    const url = new URL('/v1/search', options.baseURL)
    url.searchParams.set('q', request.query)
    url.searchParams.set('limit', String(limit))
    let body: unknown
    let resp: Response
    try {
      resp = await fetch(url, {
        headers: { Authorization: `Bearer ${token}` },
        signal,
      })
      body = await resp.json()
    } catch (err) {
      if (err instanceof WebError) throw err
      throw new WebError(`SearchHub search failed: ${(err as Error).message ?? String(err)}`, 'WEB_PROVIDER_ERROR')
    }
    const payload = body as { success?: boolean; data?: { web?: Array<Record<string, unknown>> }; error?: string }
    if (!resp.ok || payload.success === false || !payload.data?.web) {
      throw new WebError(payload.error ?? `SearchHub search http ${resp.status}`, 'WEB_PROVIDER_ERROR')
    }
    const sources = payload.data.web
      .map((item) => mapSource(item as { title?: string; url?: string; description?: string; published_at?: string | null }))
      .filter((s): s is WebSearchSource => s !== undefined)
    return { sources, truncated: false }
  }
}

export class SearchHubFetchProvider implements WebFetchProvider {
  readonly id = 'searchhub'

  constructor(private readonly resolveOptions: () => SearchHubProviderOptions) {}

  available(): boolean {
    return isAvailable(this.resolveOptions())
  }

  async fetch(request: WebFetchRequest, signal?: AbortSignal): Promise<WebFetchResult> {
    const options = this.resolveOptions()
    const token = await requireToken(options)
    let resp: Response
    let body: unknown
    try {
      resp = await fetch(new URL('/v1/extract', options.baseURL), {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ urls: [request.url], format: 'markdown' }),
        signal,
      })
      body = await resp.json()
    } catch (err) {
      if (err instanceof WebError) throw err
      throw new WebError(`SearchHub fetch failed: ${(err as Error).message ?? String(err)}`, 'WEB_PROVIDER_ERROR')
    }
    const payload = body as { success?: boolean; data?: Array<Record<string, unknown>>; error?: string }
    if (!resp.ok || payload.success === false) {
      throw new WebError(payload.error ?? `SearchHub extract http ${resp.status}`, 'WEB_PROVIDER_ERROR')
    }
    const item = (payload.data ?? []).find((it) => it.url === request.url)
    if (!item) {
      throw new WebError(`SearchHub extract returned no result for ${request.url}`, 'WEB_PROVIDER_ERROR')
    }
    if (item.error) {
      throw new WebError(String(item.error), 'WEB_PROVIDER_ERROR')
    }
    return {
      url: request.url,
      statusCode: 200,
      truncated: false,
      body: { kind: 'text', content: String(item.content ?? item.raw_content ?? '') },
    }
  }
}
