# SearchHub M2B-followup-2：供应商目录（Catalog）式配置实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将供应商配置从"统一表单 + 手输 id"改为"目录式"：列表页展示全部支持的供应商（含配置状态），点击进入**按类型渲染的专属表单**（字段/校验/提示随供应商类型变化）。后端零改动。

**Architecture:** 前端新增静态注册表 `frontend/src/api/providerCatalog.ts`（与后端 PROVIDER_CLASSES 一一对应）：每个条目含 type/name/描述 i18n key/可选能力集/需 Key 否/需 base_url 否。ProvidersView 拆两段：已配置列表 + 可用供应商卡片目录；ProviderDetailView 按 `catalogEntry(type)` 渲染表单（base_url 仅 searxng 显示且必填、capabilities 只列该类型可用项、Key 型显示"保存后添加"提示、零配置型隐藏无关字段）。路由：新建 `/providers/new/:type`，编辑 `/providers/:id` 不变。

**Tech Stack:** 现有 Vue3/Naive UI 栈；无新依赖。

## Global Constraints

- 后端不改一行（提交的 ProviderConfig 结构不变）；pytest 166 保持全绿
- 目录静态表覆盖全部 6 个现有 adapter：exa/tavily（search+extract，需 Key）、ddg（search，零配置）、searxng（search，需 base_url）、jina（extract，可选 Key）、trafilatura（extract，零配置）
- 路由：`/providers/new/:type`（新建，type ∈ 目录）；`/providers/:id`（编辑，向后兼容现有已配置供应商，含目录外自定义 id——表单按已加载配置渲染）
- 新建默认 capabilities = 该类型全部可用项；表单校验：capabilities 非空（沿用）、base_url 必填类型必填校验
- i18n zh/en 完整；vitest + build 全绿；提交风格 `feat:`/`fix:`/`chore:`

## File Structure

```
frontend/src/
  api/providerCatalog.ts          # 目录注册表 + catalogEntry()
  views/ProvidersView.vue         # 两段式：已配置列表 + 目录卡片
  views/ProviderDetailView.vue    # 按类型渲染表单
  router/index.ts                 # + /providers/new/:type
  i18n/index.ts                   # + providers.* 目录键（zh/en）
frontend/tests/
  provider-catalog.test.ts        # 注册表完整性测试
```

---

### Task 1: 目录注册表 + 列表页目录视图 + 路由

**Files:**
- Create: `frontend/src/api/providerCatalog.ts`
- Modify: `frontend/src/views/ProvidersView.vue`（两段式重构）
- Modify: `frontend/src/router/index.ts`（新路由）
- Modify: `frontend/src/i18n/index.ts`（目录相关键）
- Test: `frontend/tests/provider-catalog.test.ts`

**Interfaces:**
- Produces（providerCatalog.ts）:
```ts
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
```
> 说明：`requiresKey` 语义 = "需要/建议 Key 配置"（exa/tavily 必须；jina 为可选，但目录统一标 false + 详情页提示可选——见 Task 2 的 jina 特判）。保持目录简单：`requiresKey: true` 仅 exa/tavily；jina 的"可选 Key"提示由详情页对 type==='jina' 特判展示。

- Produces（router）: 新增路由（放在 `providers/:id` **之前**，避免 `new` 被 `:id` 吃掉）:
```ts
{ path: 'providers/new/:type', name: 'provider-new', component: () => import('@/views/ProviderDetailView.vue'), props: (route) => ({ id: 'new', type: String(route.params.type) }) },
```
（`providers/:id` 保留，props: true）

- Produces（ProvidersView.vue 两段式）:
  - 上段「已配置供应商」`n-data-table`（现状保留：id/能力/启停/权重/优先级/操作：查看详情/删除确认）
  - 下段「可用供应商」目录卡片网格（`n-grid` + `n-card`，每目录条目一张）：名称、描述（`t(descKey)`）、能力 `n-tag` 列表、状态 `n-tag`（已配置=该 id 出现在 config.providers / 未配置）、点击卡片 → 已配置进 `/providers/{id}`，未配置进 `/providers/new/{type}`
  - "新增供应商"按钮改为仅跳转目录首卡（或移除按钮——目录即入口；保留按钮滚动到目录区）
- Produces（i18n）: `providers.configuredTitle`（zh "已配置供应商" / en "Configured providers"）、`providers.catalogTitle`（zh "可用供应商" / en "Available providers"）、`providers.configured`（zh "已配置" / en "Configured"）、`providers.unconfigured`（zh "未配置" / en "Not configured"）、`providers.desc.exa`（zh "云端搜索与提取 API，支持多 Key 轮换" / en "Cloud search & extract API with multi-key rotation"）、`providers.desc.tavily`（同风格）、`providers.desc.ddg`（zh "DuckDuckGo 元搜索，免 Key" / en "DuckDuckGo metasearch, no key"）、`providers.desc.searxng`（zh "自建 SearXNG 实例（JSON API）" / en "Self-hosted SearXNG instance (JSON API)"）、`providers.desc.jina`（zh "Jina Reader 网页提取（可选免费 Key）" / en "Jina Reader extract (optional free key)"）、`providers.desc.trafilatura`（zh "本地轻量网页提取，免 Key" / en "Local lightweight extract, no key"）
- Produces（测试）: `frontend/tests/provider-catalog.test.ts`:
```ts
import { describe, expect, it } from 'vitest'
import { PROVIDER_CATALOG, catalogEntry } from '@/api/providerCatalog'

describe('provider catalog', () => {
  it('covers all six supported providers with unique types', () => {
    const types = PROVIDER_CATALOG.map((e) => e.type)
    expect(types).toEqual(['exa', 'tavily', 'ddg', 'searxng', 'jina', 'trafilatura'])
    expect(new Set(types).size).toBe(types.length)
  })

  it('has non-empty names and desc keys', () => {
    for (const e of PROVIDER_CATALOG) {
      expect(e.name.length).toBeGreaterThan(0)
      expect(e.descKey.startsWith('providers.desc.')).toBe(true)
    }
  })

  it('exa and tavily require keys; searxng requires base url', () => {
    expect(catalogEntry('exa')?.requiresKey).toBe(true)
    expect(catalogEntry('tavily')?.requiresKey).toBe(true)
    expect(catalogEntry('searxng')?.requiresBaseUrl).toBe(true)
    expect(catalogEntry('ddg')?.requiresKey).toBe(false)
  })

  it('capabilities are valid subsets', () => {
    for (const e of PROVIDER_CATALOG) {
      for (const c of e.capabilities) {
        expect(['search', 'extract']).toContain(c)
      }
    }
  })

  it('returns undefined for unknown type', () => {
    expect(catalogEntry('nope')).toBeUndefined()
  })
})
```

- [ ] **Step 1: 写失败测试**

按 Interfaces 写 `provider-catalog.test.ts`（含 catalogEntry/PROVIDER_CATALOG 断言），运行确认失败。

Run: `cd frontend && npx vitest run tests/provider-catalog.test.ts`
Expected: FAIL（模块不存在）

- [ ] **Step 2: 实现 providerCatalog.ts + i18n + 路由**

按 Interfaces 创建目录注册表；i18n 追加目录键（zh+en）；路由追加 `providers/new/:type`。

- [ ] **Step 3: 重构 ProvidersView.vue**

两段式实现；目录卡片点击跳转逻辑：
```ts
function onCatalogClick(entry: ProviderCatalogEntry) {
  const configured = configuredIds.value.has(entry.type)
  router.push(configured ? { name: 'provider-detail', params: { id: entry.type } } : { name: 'provider-new', params: { type: entry.type } })
}
```
（`configuredIds` = config.providers 的 id 集合；`n-grid :cols="3"` 响应式可用 `responsive="screen"`）

- [ ] **Step 4: 验证**

Run: `cd frontend && npm test && npm run build`
Expected: vitest 25（20 + 5 新增）+ build 通过

- [ ] **Step 5: 提交**

```bash
git add frontend/src frontend/tests/provider-catalog.test.ts
git commit -m "feat(web): provider catalog with per-type entry and configured list"
```
---

### Task 2: 详情页按类型渲染表单 + 校验

**Files:**
- Modify: `frontend/src/views/ProviderDetailView.vue`
- Modify: `frontend/src/i18n/index.ts`（详情页提示键）
- Test: `frontend/tests/provider-detail-form.test.ts`（若可测的纯逻辑；否则以 build + 验收清单为准）

**Interfaces:**
- Produces（ProviderDetailView.vue）:
  - props 扩展：`defineProps<{ id: string; type?: string }>()`
  - `const isNew = computed(() => props.id === 'new')`
  - `const entry = computed(() => isNew.value ? catalogEntry(props.type ?? '') : catalogEntry(form.id))`——新建用路由 type；编辑从已加载配置的 id 反查目录（目录外自定义 id → entry undefined，表单按通用模式渲染，向后兼容）
  - 新建默认表单：`capabilities: entry?.capabilities.slice() ?? ['search', 'extract']`；标题：`entry?.name ?? t('providers.new')`
  - 表单字段按 entry 渲染：
    - `base_url` 字段：`v-if="!isNew || entry?.requiresBaseUrl"`——新建时仅 searxng 显示；编辑时已有 base_url 的（如自定义供应商）显示
    - capabilities 复选框：只列 `entry?.capabilities ?? ['search', 'extract']`
    - Key 提示（新建时）：`entry?.requiresKey` → `n-alert` 提示 `providers.addKeyHint`（"保存后进入编辑页在 Key 池中添加 API Key"）；`props.type === 'jina'` → 提示 `providers.keyOptionalHint`（"可选：添加 JINA_KEY_1 可提升提取配额"）
  - 校验：沿用 capabilities 非空；新增 `requiresBaseUrl` 且新建时 base_url 必填（`form.base_url.trim()` 为空 → message.error(`providers.baseUrlRequired`)）
  - 保存成功：`router.replace(`/providers/${cfg.id}`)`（进入编辑态，与现有一致）
- Produces（i18n）: `providers.addKeyHint`（zh "保存后进入编辑页，在 Key 池中添加 API Key（可添加多个，自动轮换）" / en "After saving, add API keys in the key pool section (multiple keys rotate automatically)"）、`providers.keyOptionalHint`（zh "可选：添加 JINA_KEY_1 可提升免费提取配额" / en "Optional: add JINA_KEY_1 for higher free extract quota"）、`providers.baseUrlRequired`（zh "请填写 base_url（自建实例地址）" / en "base_url is required (your instance address)"）

- [ ] **Step 1: 实现详情页改造**

按 Interfaces 改造；关键渲染逻辑：
```vue
<n-form-item v-if="!isNew || entry?.requiresBaseUrl" :label="t('providers.baseUrl')">
  <n-input v-model:value="form.base_url" placeholder="http://searxng:8080" />
</n-form-item>
...
<n-alert v-if="isNew && entry?.requiresKey" type="info" :show-icon="false" class="key-hint">
  {{ t('providers.addKeyHint') }}
</n-alert>
<n-alert v-else-if="isNew && props.type === 'jina'" type="info" :show-icon="false" class="key-hint">
  {{ t('providers.keyOptionalHint') }}
</n-alert>
```
（capabilities 复选框的 options 来自 `availableCaps` computed；`onSave` 的 base_url 校验插在 capabilities 校验之后）

- [ ] **Step 2: 验证**

Run: `cd frontend && npm test && npm run build`
Expected: 全绿（vitest 25、build 通过）

- [ ] **Step 3: 手工验收清单（对照问题 2 的原意）**

1. 列表页目录区出现 6 张供应商卡（名称/描述/能力/状态标签）
2. 点击未配置的 searxng → `/providers/new/searxng`：仅 search 可勾选、显示 base_url 必填、不显示 Key 提示
3. 点击未配置的 exa → 表单仅 search+extract 可勾选、显示"保存后添加 Key"提示、无 base_url
4. 保存 exa → 跳转编辑页 → Key 池可见 → 添加 Key
5. 已配置供应商（含目录外自定义 id）在编辑页仍能正常渲染与保存
6. 目录卡状态标签随配置变化（保存后回列表 → exa 显示"已配置"）

- [ ] **Step 4: 提交**

```bash
git add frontend/src
git commit -m "feat(web): per-type provider configuration form"
```

---

## Self-Review

- **Spec 覆盖**：目录式列表（含状态）→ Task 1；按类型专属表单（base_url 条件显示、能力受限、Key 提示、必填校验）→ Task 2；后端零改动 ✓（纯前端）；向后兼容（目录外自定义 id 编辑）→ Task 2 entry 可空回退。
- **占位符扫描**：Task 1 完整代码；Task 2 关键渲染/校验代码完整。
- **类型一致性**：`catalogEntry(type)` 签名在 Task 1 注册表、Task 2 详情页、测试三处一致；路由 props 形状 `{ id: 'new', type }` 与详情页 props 一致；`providers.desc.*` 键在目录表与 i18n 一致。
- 已知取舍：jina 的"可选 Key"用 type 特判（目录表不引入 optionalKey 字段，保持简单）；自定义 id 供应商的编辑表单按通用模式（目录外无类型引导）。
