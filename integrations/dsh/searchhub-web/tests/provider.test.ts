import { afterEach, describe, expect, it, vi } from 'vitest'
import { WebError } from '@deepseek-ai/dsh-web'
import { isAvailable, SearchHubFetchProvider, SearchHubSearchProvider } from '../src/provider.js'

const base = 'http://searchhub:8000'
const opts = () => ({ baseURL: base, token: 'tok-1' })

describe('isAvailable', () => {
  it('requires parseable url and a token source', () => {
    expect(isAvailable({ baseURL: 'http://x', token: 't' })).toBe(true)
    expect(isAvailable({ baseURL: 'not a url', token: 't' })).toBe(false)
    expect(isAvailable({ baseURL: 'http://x', token: '' })).toBe(false)
    expect(isAvailable({ baseURL: 'http://x', resolveToken: async () => 't' })).toBe(true)
  })
})

describe('SearchHubSearchProvider', () => {
  const originalFetch = globalThis.fetch
  afterEach(() => { globalThis.fetch = originalFetch })

  function mockFetch(status: number, payload: unknown) {
    globalThis.fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify(payload), { status })) as unknown as typeof fetch
  }

  it('maps web results to sources', async () => {
    mockFetch(200, { success: true, data: { web: [
      { title: 'T', url: 'https://a.com', description: 'D', position: 0, published_at: '2024-01-01' },
      { url: 'https://b.com' },
    ] } })
    const provider = new SearchHubSearchProvider(opts)
    const result = await provider.search({ query: 'python', maxResults: 5 })
    expect(result.sources).toEqual([
      { url: 'https://a.com', title: 'T', snippet: 'D', publishedAt: '2024-01-01' },
      { url: 'https://b.com' },
    ])
    expect(result.truncated).toBe(false)
    const call = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string | URL, RequestInit]
    expect(String(call[0])).toContain('/v1/search?q=python&limit=5')
    expect((call[1].headers as Record<string, string>).Authorization).toBe('Bearer tok-1')
  })

  it('throws WebError on failure envelope', async () => {
    mockFetch(500, { success: false, error: 'boom' })
    await expect(new SearchHubSearchProvider(opts).search({ query: 'q' })).rejects.toThrow(WebError)
  })

  it('throws WebError on transport error', async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new Error('network down')) as unknown as typeof fetch
    await expect(new SearchHubSearchProvider(opts).search({ query: 'q' })).rejects.toThrow('network down')
  })

  it('throws WebError without token', async () => {
    await expect(new SearchHubSearchProvider(() => ({ baseURL: base, resolveToken: async () => '' })).search({ query: 'q' }))
      .rejects.toThrow(WebError)
  })

  it('propagates AbortError unchanged', async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new DOMException('The operation was aborted.', 'AbortError')) as unknown as typeof fetch
    const controller = new AbortController()
    controller.abort()
    const err = await new SearchHubSearchProvider(opts).search({ query: 'q' }, controller.signal).catch((e: unknown) => e)
    expect(err).toBeInstanceOf(DOMException)
    expect((err as DOMException).name).toBe('AbortError')
    expect(err).not.toBeInstanceOf(WebError)
  })
})

describe('SearchHubFetchProvider', () => {
  const originalFetch = globalThis.fetch
  afterEach(() => { globalThis.fetch = originalFetch })

  it('maps extract content to text body', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ success: true, data: [
      { url: 'https://a.com', content: 'hello', raw_content: 'raw' },
    ] }), { status: 200 })) as unknown as typeof fetch
    const provider = new SearchHubFetchProvider(opts)
    const result = await provider.fetch({ url: 'https://a.com' })
    expect(result.statusCode).toBe(200)
    expect(result.body).toEqual({ kind: 'text', content: 'hello' })
    expect(result.truncated).toBe(false)
  })

  it('throws WebError on per-url error', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ success: true, data: [
      { url: 'https://a.com', error: 'blocked' },
    ] }), { status: 200 })) as unknown as typeof fetch
    await expect(new SearchHubFetchProvider(opts).fetch({ url: 'https://a.com' })).rejects.toThrow(WebError)
  })

  it('throws WebError on non-JSON error body', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(new Response('gateway error', { status: 502 })) as unknown as typeof fetch
    await expect(new SearchHubFetchProvider(opts).fetch({ url: 'https://a.com' })).rejects.toThrow(WebError)
  })

  it('throws WebError when extract returns no result for url', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ success: true, data: [
      { url: 'https://other.com', content: 'x' },
    ] }), { status: 200 })) as unknown as typeof fetch
    await expect(new SearchHubFetchProvider(opts).fetch({ url: 'https://a.com' })).rejects.toThrow('returned no result')
  })

  it('propagates AbortError unchanged', async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new DOMException('The operation was aborted.', 'AbortError')) as unknown as typeof fetch
    const controller = new AbortController()
    controller.abort()
    const err = await new SearchHubFetchProvider(opts).fetch({ url: 'https://a.com' }, controller.signal).catch((e: unknown) => e)
    expect(err).toBeInstanceOf(DOMException)
    expect((err as DOMException).name).toBe('AbortError')
    expect(err).not.toBeInstanceOf(WebError)
  })
})
