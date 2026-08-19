import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { onUnauthorized, setOnUnauthorized } from '@/api/client'
import { useAuthStore } from '@/stores/auth'

describe('auth store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    setOnUnauthorized(() => {})
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

  it('failed login rejects with error message', async () => {
    const store = useAuthStore()
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ success: false, error: 'invalid credentials' }), { status: 401 }),
    )
    await expect(store.login('admin', 'wrong')).rejects.toThrow('invalid credentials')
    expect(store.loggedIn).toBe(false)
  })

  it('isDefaultPassword true when config reports default password', async () => {
    const store = useAuthStore()
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ success: true, data: { password_is_default: true } }), { status: 200 }),
    )
    expect(await store.isDefaultPassword()).toBe(true)
    expect(fetchMock.mock.calls[0][0]).toBe('/api/admin/config')
  })

  it('isDefaultPassword false when password has been changed', async () => {
    const store = useAuthStore()
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ success: true, data: { password_is_default: false } }), { status: 200 }),
    )
    expect(await store.isDefaultPassword()).toBe(false)
  })

  it('setOnUnauthorized replaces the hook and restores the original', () => {
    const original = onUnauthorized
    const spy = vi.fn()
    setOnUnauthorized(spy)
    expect(onUnauthorized).toBe(spy)
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ success: false, error: 'unauthorized' }), { status: 401 }),
    )
    const store = useAuthStore()
    return store.checkSession().then((ok) => {
      expect(ok).toBe(false)
      expect(spy).toHaveBeenCalled()
      setOnUnauthorized(original)
      expect(onUnauthorized).toBe(original)
    })
  })
})
