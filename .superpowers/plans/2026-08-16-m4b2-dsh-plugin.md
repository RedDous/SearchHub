# SearchHub M4B-2：dsh（DeepSeek Harness）插件实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付 dsh 的 SearchHub web 能力插件（npm 包 `integrations/dsh/searchhub-web/`）：按 dsh 官方 web seam 契约注册 **search provider**（调 SearchHub `/v1/search`）与 **fetch provider**（调 `/v1/extract`），支持设置段（baseURL/token 凭据引用）与环境变量回退。dsh 是 dev-preview，接口以**安装到本地的 rc 包类型为准**（已核对：`@deepseek-ai/dsh-web@0.0.1-rc.1` 等全部发布）。

**Architecture:** 插件结构镜像 dsh 官方 `packages/web/web-search-deepseek`：`src/provider.ts`（实现 `WebSearchProvider`/`WebFetchProvider` 接口，构造注入 options 以可单测）+ `src/index.ts`（Cordis 插件：`name`/`inject: ['web']`/`apply(ctx, config)`，`installSettingsSection` 注册设置段，`ctx.web.registerSearchProvider/registerFetchProvider` 注册）。搜索映射：`data.web[]` → `{url, title, description→snippet, published_at→publishedAt}`；提取映射：单 URL → `{url, statusCode: 200, body: {kind: 'text', text: content}}`；失败（非 200/信封 error/网络异常）→ `throw new WebError(msg, 'WEB_PROVIDER_ERROR')`。配置：`Config { baseURL?, token?(secret), tokenEnv?(credential-ref, 默认 SEARCHHUB_TOKEN) }`，env 回退 `SEARCHHUB_URL`/`SEARCHHUB_TOKEN` 经 `launchEnvironmentOf`。

**Tech Stack:** TypeScript、Cordis 插件规范、`@deepseek-ai/dsh-web`/`dsh-settings`/`dsh-credentials`/`dsh-launch-environment`/`dsh-agent`/`cordis`/`schemastery`（devDeps 固定 rc 版本）；vitest 单测；tsc 构建。

## Global Constraints

- 插件包名 `searchhub-dsh-web`（version 0.1.0，private 不发布）；peerDependencies 声明 dsh 运行时包（>=0.0.1-rc.1），devDependencies 固定 rc 版本用于本地类型检查/测试
- provider 接口（按已核对契约）：`id: string`、`available(): boolean`（URL 可解析 && (字面 token 或 resolveToken 存在)）、`search(request: WebSearchRequest, signal?: AbortSignal): Promise<WebSearchResult>`、`fetch?`——fetch 对应 seam 为 `WebFetchRequest{url}` → `WebFetchResult{url, statusCode, body}`；具体方法名/类型以安装版本为准，偏差记录
- 映射：`WebSearchResult{content?, sources[], truncated: false}`（truncated 由 seam 截断，provider 恒 false，与官方 deepseek provider 一致）；`WebSearchSource{url, title?, snippet?, publishedAt?}`
- 失败一律 `throw WebError(message, 'WEB_PROVIDER_ERROR')`（从 `@deepseek-ai/dsh-web` 导入）；transport/非 2xx/信封 success=false 均走此路径；绝不在错误里带 token
- `available()` 不联网；token 解析优先字面值、否则 `resolveToken`（credentials.resolve(credentialRef) → env 回退）
- 构建：`tsc` 产出 `lib/`；测试：vitest（provider 单测必过；apply 接线测试用最小 fake ctx，best-effort——不可行则记录并仅类型检查）
- 仓库内 `integrations/dsh/searchhub-web/node_modules/` 与 `lib/` gitignore；集成件不影响主 pytest 175/前端
- 提交风格 `feat:`/`fix:`/`chore:`

## File Structure

```
integrations/dsh/searchhub-web/
  package.json          # name/peer/dev deps/scripts(build,test)/main lib/index.js
  tsconfig.json         # strict, ESM, outDir lib, types
  README.md             # 安装（dsh 插件机制按当时版本）、配置（env/设置段）、验证
  .gitignore            # node_modules/ lib/
  src/
    provider.ts         # SearchHubSearchProvider + SearchHubFetchProvider
    index.ts            # name/inject/Config/apply + settings section + 注册
  tests/
    provider.test.ts    # available/search/fetch/error 映射（mock fetch）
    apply.test.ts       # fake ctx 注册断言（best-effort）
```

---

### Task 1: 插件包 scaffold + provider.ts + 单测

**Files:**
- Create: `integrations/dsh/searchhub-web/package.json`、`tsconfig.json`、`.gitignore`、`src/provider.ts`
- Create: `integrations/dsh/searchhub-web/tests/provider.test.ts`
- 根 `.gitignore` 追加 `integrations/dsh/**/node_modules/`、`integrations/dsh/**/lib/`

**Interfaces:**
- Produces `provider.ts`（完整实现；options 注入便于测试）:
```ts
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
    try {
      const resp = await fetch(url, {
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
      throw new WebError(payload.error ?? `SearchHub search http ${(resp as Response).status}`, 'WEB_PROVIDER_ERROR')
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
    try {
      resp = await fetch(new URL('/v1/extract', options.baseURL), {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ urls: [request.url], format: 'markdown' }),
        signal,
      })
    } catch (err) {
      throw new WebError(`SearchHub fetch failed: ${(err as Error).message ?? String(err)}`, 'WEB_PROVIDER_ERROR')
    }
    const body = (await resp.json()) as { success?: boolean; data?: Array<Record<string, unknown>>; error?: string }
    if (!resp.ok || body.success === false) {
      throw new WebError(body.error ?? `SearchHub extract http ${resp.status}`, 'WEB_PROVIDER_ERROR')
    }
    const item = (body.data ?? []).find((it) => it.url === request.url)
    if (!item) {
      throw new WebError(`SearchHub extract returned no result for ${request.url}`, 'WEB_PROVIDER_ERROR')
    }
    if (item.error) {
      throw new WebError(String(item.error), 'WEB_PROVIDER_ERROR')
    }
    return {
      url: request.url,
      statusCode: 200,
      body: { kind: 'text', text: String(item.content ?? item.raw_content ?? '') },
    }
  }
}
```
> 注：`WebFetchProvider`/`WebFetchBody` 的确切方法名与 kind 取值以安装的 `@deepseek-ai/dsh-web` 类型为准——若 `registerFetchProvider`/`WebFetchResult.body` 形状不同，按实际调整并记录偏差（契约意图不变：单 URL 提取 → 200 + 文本 body）。

- Produces `package.json`:
```json
{
  "name": "searchhub-dsh-web",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "description": "SearchHub search and fetch providers for the DeepSeek Harness web seam (ctx.web)",
  "main": "lib/index.js",
  "types": "lib/types/index.d.ts",
  "scripts": {
    "build": "tsc -p tsconfig.json",
    "test": "vitest run",
    "typecheck": "tsc -p tsconfig.json --noEmit"
  },
  "peerDependencies": {
    "@deepseek-ai/cordis": ">=4.0.1",
    "@deepseek-ai/dsh-agent": ">=0.0.1-rc.1",
    "@deepseek-ai/dsh-credentials": ">=0.0.1-rc.1",
    "@deepseek-ai/dsh-launch-environment": ">=0.0.1-rc.3",
    "@deepseek-ai/dsh-settings": ">=0.0.1-rc.1",
    "@deepseek-ai/dsh-web": ">=0.0.1-rc.1"
  },
  "devDependencies": {
    "@deepseek-ai/cordis": "4.0.1",
    "@deepseek-ai/dsh-agent": "0.0.1-rc.1",
    "@deepseek-ai/dsh-credentials": "0.0.1-rc.1",
    "@deepseek-ai/dsh-launch-environment": "0.0.1-rc.3",
    "@deepseek-ai/dsh-settings": "0.0.1-rc.1",
    "@deepseek-ai/dsh-web": "0.0.1-rc.1",
    "@deepseek-ai/schemastery": "^3.18.1",
    "typescript": "~5.9.3",
    "vitest": "^3.2.7"
  }
}
```
（若某 devDep 的 rc 版本与 peer 声明冲突导致 npm 安装失败，调整至可安装版本并记录。）

- Produces `tsconfig.json`: strict、`module: "ESNext"`、`moduleResolution: "bundler"`、`target: "ES2022"`、`outDir: "lib"`、`declaration: true`、`declarationDir: "lib/types"`、include `src` + `tests`
- Produces `tests/provider.test.ts`（vitest，mock 全局 fetch）:
```ts
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
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
    expect(result.body).toEqual({ kind: 'text', text: 'hello' })
  })

  it('throws WebError on per-url error', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ success: true, data: [
      { url: 'https://a.com', error: 'blocked' },
    ] }), { status: 200 })) as unknown as typeof fetch
    await expect(new SearchHubFetchProvider(opts).fetch({ url: 'https://a.com' })).rejects.toThrow(WebError)
  })
})
```
> 注：`WebFetchProvider` 接口方法名若是 `fetch` 而非其他（按安装类型核对），偏差记录；`import ... from '../src/provider.js'` 为 ESM + vitest 惯例（也可用无 .js 后缀，按 tsc/vitest 实际配置）。

- 根 `.gitignore` 追加：
```
integrations/dsh/**/node_modules/
integrations/dsh/**/lib/
```

- [ ] **Step 1: 安装依赖并核对类型**

Run: `cd integrations/dsh/searchhub-web && npm install && npx tsc --noEmit`
Expected: 安装成功；类型检查通过或给出需调整的具体类型差异（如 WebFetchProvider 方法名、WebFetchBody.kind 取值）——按实际调整 provider.ts 并记录

- [ ] **Step 2: 写失败测试**

创建 `tests/provider.test.ts`，运行 `npx vitest run tests/provider.test.ts`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现**

按 Interfaces 创建 package.json/tsconfig/.gitignore/provider.ts。

- [ ] **Step 4: 验证**

Run: `cd integrations/dsh/searchhub-web && npx vitest run && npm run build`
Expected: 全部单测通过；tsc 构建产出 lib/

- [ ] **Step 5: 提交**

```bash
git add integrations/dsh .gitignore
git commit -m "feat(dsh): searchhub web provider package with unit tests"
```
---

### Task 2: apply() 接线（settings 段 + 注册）+ 接线测试 + README

**Files:**
- Create: `integrations/dsh/searchhub-web/src/index.ts`
- Create: `integrations/dsh/searchhub-web/README.md`
- Create: `integrations/dsh/searchhub-web/tests/apply.test.ts`（best-effort）
- Modify: `integrations/README.md`（dsh 条目）

**Interfaces:**
- Produces `src/index.ts`（镜像官方 web-search-deepseek 模式）:
```ts
import type { Context } from '@deepseek-ai/cordis'
import z from '@deepseek-ai/schemastery'
import type {} from '@deepseek-ai/dsh-web'
import { credentialRef } from '@deepseek-ai/dsh-credentials'
import { installSettingsSection, settingsNamespace } from '@deepseek-ai/dsh-settings'
import { launchEnvironmentOf } from '@deepseek-ai/dsh-launch-environment'
import { SearchHubFetchProvider, SearchHubSearchProvider, isAvailable, type SearchHubProviderOptions } from './provider.ts'

export const name = 'searchhub-dsh-web'
export const inject = ['web']

const DEFAULT_URL_ENV = 'SEARCHHUB_URL'
const DEFAULT_TOKEN_ENV = 'SEARCHHUB_TOKEN'

export interface Config {
  baseURL?: string
  token?: string
  tokenEnv?: string
}

export const Config: z<Config> = z.object({
  baseURL: z.string().role('url'),
  token: z.string().role('secret'),
  tokenEnv: z.string().role('credential-ref').default(DEFAULT_TOKEN_ENV),
})

export const WEB_SEARCHHUB_SETTINGS_NAMESPACE = settingsNamespace('searchhub-dsh-web')

function resolveOptions(ctx: Context, config: Config): SearchHubProviderOptions {
  const tokenEnv = credentialRef(config.tokenEnv ?? DEFAULT_TOKEN_ENV)
  const literalToken = config.token !== undefined && config.token.length > 0 ? config.token : undefined
  return {
    ...(literalToken === undefined ? {} : { token: literalToken }),
    resolveToken: async () => {
      const credentials = ctx.get('credentials')
      if (credentials !== undefined) return (await credentials.resolve(tokenEnv))?.value
      const ambient = launchEnvironmentOf(ctx).get(tokenEnv)
      return ambient !== undefined && ambient.value.length > 0 ? ambient.value : undefined
    },
    baseURL: config.baseURL ?? launchEnvironmentOf(ctx).get(DEFAULT_URL_ENV)?.value ?? 'http://127.0.0.1:8000',
  }
}

export function apply(ctx: Context, config: Config): void {
  let current: () => Config = () => config
  installSettingsSection(ctx, WEB_SEARCHHUB_SETTINGS_NAMESPACE, Config, config, {
    setSource: (source) => { current = source },
    onChange: () => {},
  })
  const opts = () => resolveOptions(ctx, current())
  ctx.web.registerSearchProvider(new SearchHubSearchProvider(opts))
  ctx.web.registerFetchProvider(new SearchHubFetchProvider(opts))
}
```
> 注：`installSettingsSection` 的签名、`ctx.web.registerFetchProvider` 是否存在、`z.string().role('url')` 取值——均以安装版本为准，偏差记录。

- Produces `README.md`（安装/配置/验证）:
  - 说明：dsh 官方 web seam 的 SearchHub 供应商（search + fetch 双能力）；配置三选：设置段 UI（baseURL/token）、环境变量（SEARCHHUB_URL/SEARCHHUB_TOKEN）、字面 token（config）
  - 安装：dsh 处于 dev-preview，插件安装机制以其当前版本为准——本地包安装（`npm install <repo>/integrations/dsh/searchhub-web`）或 dsh 插件目录复制/链接；`npm run build` 产出 lib/
  - 验证：dsh 中发起 web search 应命中 SearchHub 历史记录；无 token 时报错提示配置
- Produces `tests/apply.test.ts`（best-effort，fake ctx 捕获注册）:
```ts
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
```
> 若 fake ctx 因 `installSettingsSection` 需要更多 seam 而无法跑通，记录并仅保留 provider 单测 + 类型检查（apply 为薄接线）。

- Modify `integrations/README.md`：接入清单补 dsh 插件条目（路径 + 一句话说明）

- [ ] **Step 1: 写测试（best-effort）**

创建 `tests/apply.test.ts`，运行 `npx vitest run tests/apply.test.ts`
Expected: FAIL 或暴露 fake ctx 不足——按实际调整；若不可行记录并跳过该测试文件（不进提交）

- [ ] **Step 2: 实现 index.ts + README + 总览更新**

按 Interfaces 实现；类型检查通过（`npx tsc --noEmit`）。

- [ ] **Step 3: 验证**

Run: `cd integrations/dsh/searchhub-web && npx vitest run && npm run build`
Expected: provider 单测全过；apply 测试（若保留）通过；构建产出 lib/

- [ ] **Step 4: 全量回归 + 提交**

Run: `.venv/bin/pytest -q`
Expected: 185 全绿（集成件不影响主仓）

```bash
git add integrations/dsh integrations/README.md
git commit -m "feat(dsh): cordis apply wiring with settings section and README"
```

---

## Self-Review

- **Spec 覆盖**（设计文档 §四 dsh）：dsh 插件 → Task 1-2（search + fetch 双 provider、设置段、凭据引用、env 回退）；MCP 替代路径已在 M3 README（插件之外仍可用）；integrations/README 更新。
- **占位符扫描**：Task 1 provider.ts 完整代码与 5 个测试；Task 2 index.ts/README 内容完整。
- **类型一致性**：`SearchHubProviderOptions{baseURL, token?, resolveToken?}` 在 provider.ts 构造、index.ts resolveOptions、测试三处一致；映射字段（title/url/description/published_at）与 REST `/v1/search` 响应一致；`WebError(code='WEB_PROVIDER_ERROR')` 与 dsh 契约一致。
- 已知取舍：dsh dev-preview——接口以安装版本为准（Task 1 Step 1 先行核对类型）；apply 接线测试 best-effort（fake ctx 能力有限则跳过，provider 单测是主要保障）；fetch provider 的 body kind 以安装类型为准；插件不发布 npm（仓库内随 SearchHub 分发，README 说明安装方式）。
