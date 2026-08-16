import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, onUnauthorized, request } from '@/api/client'

describe('api client', () => {
  const originalFetch = globalThis.fetch

  function mockFetch(status: number, body: unknown) {
    globalThis.fetch = vi.fn().mockImplementation(() =>
      Promise.resolve(
        new Response(JSON.stringify(body), {
          status,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    )
  }

  afterEach(() => {
    globalThis.fetch = originalFetch
    onUnauthorized = () => {
      window.location.href = '/login'
    }
  })

  it('returns data on success envelope', async () => {
    mockFetch(200, { success: true, data: { hello: 'world' } })
    const data = await request<{ hello: string }>('/api/admin/x')
    expect(data.hello).toBe('world')
    const init = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0][1] as RequestInit
    expect(init.credentials).toBe('same-origin')
  })

  it('throws ApiError with message on failure envelope', async () => {
    mockFetch(200, { success: false, error: 'boom' })
    await expect(request('/api/admin/x')).rejects.toThrow('boom')
  })

  it('throws ApiError with status on http error', async () => {
    mockFetch(401, { success: false, error: 'unauthorized' })
    await expect(request('/api/admin/x')).rejects.toMatchObject({ status: 401 })
  })

  it('calls onUnauthorized on 401', async () => {
    const seen: string[] = []
    onUnauthorized = () => {
      seen.push('unauthorized')
    }
    mockFetch(401, { success: false, error: 'unauthorized' })
    await expect(request('/api/admin/x')).rejects.toThrow()
    expect(seen).toEqual(['unauthorized'])
  })

  it('serializes params and body', async () => {
    mockFetch(200, { success: true, data: null })
    await request('/api/admin/history', { params: { limit: 10, q: 'a b' } })
    const call = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit]
    expect(call[0]).toContain('/api/admin/history?limit=10&q=a+b')
    await request('/api/admin/tokens', { method: 'POST', body: { name: 'x' } })
    const call2 = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[1] as [string, RequestInit]
    expect(call2[1].method).toBe('POST')
    expect(call2[1].headers).toMatchObject({ 'Content-Type': 'application/json' })
  })
})
