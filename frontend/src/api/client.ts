export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

export let onUnauthorized: () => void = () => {
  window.location.href = '/login'
}

export function setOnUnauthorized(fn: () => void): void {
  onUnauthorized = fn
}

export async function request<T>(
  path: string,
  options: { method?: string; body?: unknown; params?: Record<string, string | number | undefined> } = {},
): Promise<T> {
  const { method = 'GET', body, params } = options
  let url = path
  if (params) {
    const qs = new URLSearchParams()
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== '') qs.set(k, String(v))
    }
    const s = qs.toString()
    if (s) url += `?${s}`
  }
  const init: RequestInit = { method, credentials: 'same-origin' }
  if (body !== undefined) {
    init.headers = { 'Content-Type': 'application/json' }
    init.body = JSON.stringify(body)
  }
  const resp = await fetch(url, init)
  type Envelope = { success: boolean; data?: T; error?: string } | null
  let payload: Envelope
  try {
    payload = (await resp.json()) as Envelope
  } catch {
    payload = null
  }
  if (resp.status === 401) {
    onUnauthorized()
  }
  if (!resp.ok) {
    throw new ApiError(resp.status, payload?.error ?? `HTTP ${resp.status}`)
  }
  if (!payload || payload.success === false) {
    throw new ApiError(resp.status, payload?.error ?? 'request failed')
  }
  return payload.data as T
}
