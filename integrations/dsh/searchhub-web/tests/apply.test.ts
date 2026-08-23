import { describe, expect, it, vi } from 'vitest'
import { apply } from '../src/index.js'

function fakeCtx() {
  const registered: string[] = []
  return {
    web: {
      registerSearchProvider: vi.fn((p: { id: string }) => registered.push(`search:${p.id}`)),
      registerFetchProvider: vi.fn((p: { id: string }) => registered.push(`fetch:${p.id}`)),
    },
    get: () => undefined,
    launchEnvironmentOf: () => ({ get: () => undefined }),
    inject: () => {},
    _registered: registered,
  }
}

describe('apply', () => {
  it('registers both providers', () => {
    const ctx = fakeCtx() as never
    apply(ctx, {})
    expect((ctx as unknown as { _registered: string[] })._registered.sort()).toEqual(['fetch:searchhub', 'search:searchhub'])
  })
})
