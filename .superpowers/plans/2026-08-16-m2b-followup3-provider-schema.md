# SearchHub M2B-followup3：供应商配置 Schema 体系实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把供应商配置体系改为**按类型 Schema 驱动**：每个具体供应商类声明自己的配置需求（`ProviderSchema` 类属性），后端提供 `GET /api/admin/provider-types` 并做写路径校验，前端从后端拉取 schema 渲染目录与专属表单。彻底消除统一表单（ddg/searxng 不再出现 Key 池等无关字段）与前后端目录漂移。

**Architecture:** `ProviderSchema` dataclass 定义在 `providers/schema.py`；`Provider` 抽象类给保守默认值，6 个具体 adapter 各自覆盖声明。后端 `GET /api/admin/provider-types` 遍历 `PROVIDER_CLASSES` 读类属性生成（无独立表）；创建/更新供应商时按 `PROVIDER_CLASSES[id].schema` 校验（base_url 必填、能力越界），未知 id 走宽松路径（自定义供应商兼容）。前端删除静态 `providerCatalog.ts`，新增 pinia store `providerTypes`（启动拉取一次 + 缓存 + normalize 纯函数可测），目录与详情表单全部按 schema 渲染。

**Tech Stack:** 现有 FastAPI/Vue3 栈；无新依赖。

## Global Constraints

- 后端：`ProviderSchema` 字段 `type/name/capabilities/requires_key/requires_base_url/key_pool_params("none"|"rps"|"full")/show_max_results/show_options`；`Provider.schema` 类属性默认 `capabilities=()、requires_key=False、requires_base_url=False、key_pool_params="none"、show_max_results=False、show_options=False`
- 6 个 adapter 的 schema 声明（事实依据）：exa/tavily（search+extract，requires_key=True，key_pool_params="full"，show_max_results=True）、ddg（search，show_max_results=True，其余默认）、searxng（search，requires_base_url=True，key_pool_params="rps"，show_max_results=True）、jina（extract，key_pool_params="full"）、trafilatura（extract，key_pool_params="rps"）；`show_options` 全部 False（现无 adapter 消费 options）
- 校验：已知类型（id ∈ PROVIDER_CLASSES）——requires_base_url 且 base_url 为空 → 400 "searxng requires base_url"；capabilities 含 schema 允许集之外的值 → 400；未知 id 不校验（宽松，自定义供应商兼容）。requires_key **不**强制（Key 可选后加，连接测试暴露问题）
- 前端：`adminApi.getProviderTypes()`；删除 `providerCatalog.ts` 与 `provider-catalog.test.ts`；新增 `stores/providerTypes.ts`（`load()` 只拉一次、`normalizeProviderTypes(raw)` 纯函数过滤畸形条目、`byType(type)`）；目录/表单按 schema 渲染（key_pool_params none 隐藏全部三项、rps 只显示 rps_limit、full 显示三项；requires_key 控制 Key 池区；requires_base_url 控制 base_url；show_max_results；show_options）
- 表单能力勾选 = schema.capabilities；新建模式 ID 锁定 = schema.type（沿用 batch4 行为）
- i18n：描述仍走前端 `providers.desc.{type}`（zh/en），名称来自后端 schema.name
- pytest 166 基线 + 新增；vitest 25 基线调整（删 5 个静态目录测试）+ 新增；build 全绿；提交风格 `feat:`/`fix:`/`chore:`

## File Structure

```
src/searchhub/
  providers/schema.py             # ProviderSchema dataclass + validate_provider_config()
  providers/base.py               # Provider.schema 类属性（保守默认）
  providers/exa.py / tavily.py / ddg.py / searxng.py / jina.py / trafilatura_py.py  # 各自 schema 声明
  api/admin/config_routes.py      # + GET /api/admin/provider-types；create/update 校验
tests/
  test_provider_schemas.py        # 6 个 schema 断言 + 校验函数测试
  api/admin/test_config_routes.py # + provider-types 端点与 400 校验测试
frontend/src/
  api/admin.ts                    # + ProviderType 接口 + getProviderTypes()
  stores/providerTypes.ts         # pinia store + normalizeProviderTypes
  views/ProvidersView.vue         # 目录来自 store
  views/ProviderDetailView.vue    # 表单按 schema 渲染
frontend/tests/
  provider-catalog.test.ts        # 删除（静态表移除）
  provider-types-store.test.ts    # normalize + store 测试
```

---

### Task 1: 后端 ProviderSchema + 端点 + 校验

**Files:**
- Create: `src/searchhub/providers/schema.py`
- Modify: `src/searchhub/providers/base.py`、`exa.py`、`tavily.py`、`ddg.py`、`searxng.py`、`jina.py`、`trafilatura_py.py`
- Modify: `src/searchhub/api/admin/config_routes.py`
- Test: `tests/test_provider_schemas.py`、`tests/api/admin/test_config_routes.py`

**Interfaces:**
- Produces（schema.py）:
```python
from __future__ import annotations

from dataclasses import dataclass

KeyPoolParams = str  # "none" | "rps" | "full"


@dataclass(frozen=True)
class ProviderSchema:
    type: str
    name: str
    capabilities: tuple[str, ...] = ()
    requires_key: bool = False
    requires_base_url: bool = False
    key_pool_params: KeyPoolParams = "none"
    show_max_results: bool = False
    show_options: bool = False


def validate_provider_config(provider_id: str, capabilities: list[str],
                             base_url: str | None, schema: ProviderSchema | None) -> list[str]:
    """返回错误列表（空 = 通过）。未知类型（schema=None）不校验。"""
    if schema is None:
        return []
    errors: list[str] = []
    if schema.requires_base_url and not (base_url or "").strip():
        errors.append(f"{provider_id} requires base_url")
    allowed = set(schema.capabilities)
    for c in capabilities:
        if c not in allowed:
            errors.append(f"{provider_id} does not support capability {c!r}")
    return errors
```
- Produces（base.py）: `from searchhub.providers.schema import ProviderSchema`；`Provider` 类属性 `schema: ProviderSchema = ProviderSchema(type="", name="")`（保守默认，置于 capabilities 类属性旁）
- Produces（各 adapter 类属性）:
  - exa: `schema = ProviderSchema(type="exa", name="Exa", capabilities=("search", "extract"), requires_key=True, key_pool_params="full", show_max_results=True)`
  - tavily: 同上，type="tavily" name="Tavily"
  - ddg: `ProviderSchema(type="ddg", name="DuckDuckGo", capabilities=("search",), show_max_results=True)`
  - searxng: `ProviderSchema(type="searxng", name="SearXNG", capabilities=("search",), requires_base_url=True, key_pool_params="rps", show_max_results=True)`
  - jina: `ProviderSchema(type="jina", name="Jina Reader", capabilities=("extract",), key_pool_params="full")`
  - trafilatura: `ProviderSchema(type="trafilatura", name="Trafilatura", capabilities=("extract",), key_pool_params="rps")`
- Produces（config_routes.py）:
  - `GET /api/admin/provider-types` → `{"success": True, "data": {"types": [...]}}`——遍历 `PROVIDER_CLASSES`（按 id 排序）用 `dataclasses.asdict(cls.schema)` 生成
  - `create_provider`/`update_provider`：保存前校验——`schema = PROVIDER_CLASSES[body.id].schema if body.id in PROVIDER_CLASSES else None`；`errors = validate_provider_config(body.id, body.capabilities, body.base_url, schema)`；非空 → `HTTPException(400, "; ".join(errors))`
- 注意：`PROVIDER_CLASSES` 在 `providers/__init__.py` 是 {id: class} 注册表；schema.py 不 import providers 包（避免循环），校验函数只接收 schema 参数

- [ ] **Step 1: 写失败测试**

`tests/test_provider_schemas.py`:
```python
from searchhub.providers import PROVIDER_CLASSES
from searchhub.providers.schema import ProviderSchema, validate_provider_config


def test_all_six_providers_declare_schema():
    assert set(PROVIDER_CLASSES) == {"exa", "tavily", "ddg", "searxng", "jina", "trafilatura"}
    for pid, cls in PROVIDER_CLASSES.items():
        s = cls.schema
        assert isinstance(s, ProviderSchema)
        assert s.type == pid
        assert s.name
        assert set(s.capabilities) == cls.capabilities


def test_schema_flags():
    assert PROVIDER_CLASSES["exa"].schema.requires_key is True
    assert PROVIDER_CLASSES["exa"].schema.key_pool_params == "full"
    assert PROVIDER_CLASSES["ddg"].schema.requires_key is False
    assert PROVIDER_CLASSES["ddg"].schema.key_pool_params == "none"
    assert PROVIDER_CLASSES["searxng"].schema.requires_base_url is True
    assert PROVIDER_CLASSES["searxng"].schema.key_pool_params == "rps"
    assert PROVIDER_CLASSES["jina"].schema.key_pool_params == "full"
    assert PROVIDER_CLASSES["trafilatura"].schema.key_pool_params == "rps"
    for pid, cls in PROVIDER_CLASSES.items():
        assert cls.schema.show_options is False
        assert cls.schema.show_max_results == ("search" in cls.capabilities)


def test_validate_requires_base_url():
    s = PROVIDER_CLASSES["searxng"].schema
    errors = validate_provider_config("searxng", ["search"], "", s)
    assert errors and "base_url" in errors[0]
    assert validate_provider_config("searxng", ["search"], "http://searxng:8080", s) == []


def test_validate_capability_bounds():
    s = PROVIDER_CLASSES["searxng"].schema
    errors = validate_provider_config("searxng", ["search", "extract"], "http://x", s)
    assert any("extract" in e for e in errors)


def test_validate_unknown_type_is_lenient():
    assert validate_provider_config("custom-thing", ["search"], "", None) == []
```

`tests/api/admin/test_config_routes.py` 追加：
```python
def test_provider_types_endpoint(admin_client):
    r = admin_client.get("/api/admin/provider-types")
    assert r.status_code == 200
    types = {t["type"]: t for t in r.json()["data"]["types"]}
    assert set(types) == {"exa", "tavily", "ddg", "searxng", "jina", "trafilatura"}
    assert types["exa"]["requires_key"] is True
    assert types["exa"]["key_pool_params"] == "full"
    assert types["ddg"]["requires_key"] is False
    assert types["searxng"]["requires_base_url"] is True


def test_create_searxng_without_base_url_rejected(admin_client):
    r = admin_client.post("/api/admin/providers",
                          json={"id": "searxng", "capabilities": ["search"]})
    assert r.status_code == 400
    assert "base_url" in r.json()["error"]


def test_create_searxng_with_extract_rejected(admin_client):
    r = admin_client.post("/api/admin/providers",
                          json={"id": "searxng", "capabilities": ["search", "extract"],
                                "base_url": "http://searxng:8080"})
    assert r.status_code == 400
    assert "extract" in r.json()["error"]


def test_create_ddg_with_base_url_allowed(admin_client):
    # 宽松路径：非必填字段不拒绝（ddg 无 base_url 需求但提交了也不报错）
    r = admin_client.post("/api/admin/providers",
                          json={"id": "ddg", "capabilities": ["search"],
                                "base_url": "http://example.com"})
    assert r.status_code == 200
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/pytest tests/test_provider_schemas.py tests/api/admin/test_config_routes.py -v`
Expected: FAIL（schema 不存在 / 端点 404 / 校验缺失）

- [ ] **Step 3: 实现**

按 Interfaces 创建 schema.py、各 adapter 声明 schema、端点与校验。

- [ ] **Step 4: 运行确认通过 + 全量回归**

Run: `.venv/bin/pytest tests/test_provider_schemas.py tests/api/admin/test_config_routes.py -v && .venv/bin/pytest -q`
Expected: 新增通过；全量 166 + 9 = 175 全绿

- [ ] **Step 5: 提交**

```bash
git add src/searchhub/providers src/searchhub/api/admin/config_routes.py tests/test_provider_schemas.py tests/api/admin/test_config_routes.py
git commit -m "feat: per-type provider config schema, endpoint and validation"
```
---

### Task 2: 前端 Schema 驱动（store + 目录 + 专属表单）

**Files:**
- Modify: `frontend/src/api/admin.ts`（ProviderType 接口 + getProviderTypes）
- Create: `frontend/src/stores/providerTypes.ts`
- Modify: `frontend/src/views/ProvidersView.vue`（目录来自 store）
- Modify: `frontend/src/views/ProviderDetailView.vue`（表单按 schema 渲染）
- Delete: `frontend/src/api/providerCatalog.ts`、`frontend/tests/provider-catalog.test.ts`
- Create: `frontend/tests/provider-types-store.test.ts`
- Modify: `frontend/src/i18n/index.ts`（如需要调整键）

**Interfaces:**
- Produces（admin.ts）:
```ts
export interface ProviderType {
  type: string
  name: string
  capabilities: string[]
  requires_key: boolean
  requires_base_url: boolean
  key_pool_params: 'none' | 'rps' | 'full'
  show_max_results: boolean
  show_options: boolean
}
// adminApi 增加:
getProviderTypes: () => request<{ types: ProviderType[] }>('/api/admin/provider-types'),
```
- Produces（stores/providerTypes.ts）:
```ts
import { defineStore } from 'pinia'
import { adminApi, type ProviderType } from '@/api/admin'

export function normalizeProviderTypes(raw: unknown): ProviderType[] {
  if (!Array.isArray(raw)) return []
  return raw.filter((t): t is ProviderType => {
    if (typeof t !== 'object' || t === null) return false
    const x = t as Record<string, unknown>
    return typeof x.type === 'string' && x.type.length > 0 &&
      typeof x.name === 'string' &&
      Array.isArray(x.capabilities) &&
      x.capabilities.every((c) => c === 'search' || c === 'extract') &&
      ['none', 'rps', 'full'].includes(String(x.key_pool_params))
  })
}

export const useProviderTypesStore = defineStore('providerTypes', {
  state: () => ({ types: [] as ProviderType[], loaded: false, error: '' }),
  getters: {
    byType: (state) => (type: string) => state.types.find((t) => t.type === type),
  },
  actions: {
    async load(): Promise<void> {
      if (this.loaded) return
      try {
        const r = await adminApi.getProviderTypes()
        this.types = normalizeProviderTypes(r.types)
        this.loaded = true
      } catch (e) {
        this.error = e instanceof Error ? e.message : String(e)
      }
    },
  },
})
```
- Produces（ProvidersView.vue）：目录数据从 `useProviderTypesStore()` 取（`onMounted` 并行 `load()` + config 加载）；卡片渲染/点击逻辑不变（entry 类型改为 ProviderType）；store 加载失败时目录区显示错误（`store.error` + `n-alert`）
- Produces（ProviderDetailView.vue）：
  - `import { useProviderTypesStore } from '@/stores/providerTypes'`；`const typesStore = useProviderTypesStore()`；`entry = computed(() => isNew ? typesStore.byType(props.type ?? '') : typesStore.byType(form.id))`
  - 表单渲染条件：
    - base_url 字段：`v-if="isNew ? !!entry?.requires_base_url : (!!entry?.requires_base_url || !!form.base_url)"`（沿用 batch4 修正）
    - capabilities 勾选：`entry?.capabilities ?? ['search', 'extract']`
    - max_results 字段：`v-if="entry?.show_max_results ?? true"`（编辑无 entry 时显示，兼容自定义）
    - key_pool 参数：
      - `entry?.key_pool_params === 'full' || (!entry && !isNew)` → 显示 max_concurrency/rps_limit/cooldown_s 三项
      - `entry?.key_pool_params === 'rps'` → 只显示 rps_limit
      - `'none'` → 三项全隐藏
      - 新建无 entry（自定义）→ 不显示（自定义建完进编辑页再按通用显示）
    - options 字段：`v-if="entry?.show_options"`（当前全 false → 隐藏）
    - Key 池区：`v-if="entry?.requires_key || (!entry && !isNew)"`（新建自定义不显示；编辑自定义显示）
    - jina 可选提示保留（`props.type === 'jina'`）
  - 新建 ID 锁定/预填：沿用 emptyForm 用 `typesStore.byType(props.type ?? '')`；`emptyForm` 的 catalogType 取 store
- i18n：名称用 `entry.name`；描述沿用 `providers.desc.{type}`（键已存在，检查 jina/trafilatura 等均有）；无需新键（若 Key 池区在编辑自定义供应商时显示，沿用现有 `providers.keyPool` 键）
- 测试（provider-types-store.test.ts）:
```ts
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { normalizeProviderTypes, useProviderTypesStore } from '@/stores/providerTypes'

describe('normalizeProviderTypes', () => {
  it('filters malformed entries', () => {
    const raw = [
      { type: 'exa', name: 'Exa', capabilities: ['search', 'extract'], key_pool_params: 'full' },
      { type: 'bad', name: '', capabilities: ['crawl'], key_pool_params: 'weird' },
      null,
      'nope',
    ]
    const types = normalizeProviderTypes(raw)
    expect(types).toHaveLength(1)
    expect(types[0].type).toBe('exa')
  })
})

describe('provider types store', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('loads once and caches', async () => {
    const store = useProviderTypesStore()
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ success: true, data: { types: [
        { type: 'ddg', name: 'DuckDuckGo', capabilities: ['search'], key_pool_params: 'none' },
      ] } }), { status: 200 }),
    )
    await store.load()
    await store.load()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(store.types[0].type).toBe('ddg')
    expect(store.byType('ddg')?.name).toBe('DuckDuckGo')
  })
})
```

- [ ] **Step 1: 写失败测试 + 删旧测试**

创建 `provider-types-store.test.ts`；删除 `provider-catalog.test.ts`。
Run: `cd frontend && npx vitest run tests/provider-types-store.test.ts`
Expected: FAIL（模块不存在）

- [ ] **Step 2: 实现**

按 Interfaces 实现（admin.ts 接口、store、两个视图改造、删除静态目录文件）。

- [ ] **Step 3: 验证**

Run: `cd frontend && npm test && npm run build`
Expected: vitest 通过（25 - 5 旧 + 3 新 = 23）；build 全绿

- [ ] **Step 4: 回归 + 提交**

Run: `.venv/bin/pytest -q`
Expected: 175 全绿

```bash
git add frontend/src frontend/tests
git commit -m "feat(web): schema-driven provider catalog and forms from backend"
```

---

## Self-Review

- **Spec 覆盖**：执行层抽象类已有（base.py + 6 adapter）✓；配置层 schema 挂到具体类 → Task 1；后端端点 + 写路径校验 → Task 1；前端删除静态表、store 拉取、目录/表单按 schema 渲染（key_pool_params 三态、requires_key 控制 Key 池区、base_url、max_results、options 全隐藏）→ Task 2；测试两端。
- **占位符扫描**：Task 1 完整代码；Task 2 store/测试完整、视图渲染条件明确。
- **类型一致性**：`ProviderSchema` 字段名（snake_case）在后端 dataclass、端点 JSON、前端 `ProviderType` 接口、store normalize 四者一致；`key_pool_params` 三态字符串在两端一致；`byType` 命名在视图与测试一致。
- 已知取舍：`show_options` 全 false（options 字段当前无 adapter 消费，隐藏；后续实现消费时把对应 adapter 的 schema.show_options 置 true 即可）；requires_key 不强制校验（Key 可在保存后添加，连接测试暴露缺失）；自定义（未知 id）供应商新建时按通用表单（无 schema 引导），保存后进编辑页按通用模式显示。
