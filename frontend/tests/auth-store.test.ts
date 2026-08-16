import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAuthStore } from '@/stores/auth'

describe('auth store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('checkSession true on 200 config', async () => {
    const store = useAuthStore()
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ success: true, data: {} }), { status: 200 }),
    )
    expect(await store.checkSession()).toBe(true)
    expect(store.loggedIn).toBe(true)
  })

  it('checkSession false on 401', async () => {
    const store = useAuthStore()
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ success: false, error: 'unauthorized' }), { status: 401 }),
    )
    expect(await store.checkSession()).toBe(false)
    expect(store.loggedIn).toBe(false)
  })

  it('login posts credentials and sets loggedIn', async () => {
    const store = useAuthStore()
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ success: true, data: { username: 'admin' } }), { status: 200 }),
    )
    await store.login('admin', 'secret')
    expect(store.loggedIn).toBe(true)
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/admin/login')
    expect(JSON.parse(String(init.body))).toEqual({ username: 'admin', password: 'secret' })
  })
})
