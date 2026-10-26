# 供应商配置架构重构设计（FieldSpec v0）

> 日期：2026-10-25
> 状态：草稿（待评审）
> 范围：供应商配置模型、ProviderSchema / FieldSpec、管理端交互、迁移清单
> 不包含：具体代码实现、per-request options、完整多实例管理 UI

## 一、背景与结论

当前供应商配置是“通用表单 + 少量布尔开关 + adapter 内硬编码差异”：

- `ProviderConfig` 只有 `id`、`capabilities`、`enabled`、`weight`、`priority`、`max_results`、`base_url`、`key_pool`、`options`（`config.py:44-53`）；
- `ProviderSchema` 只有 9 个字段，主要是 UI 开关（`providers/schema.py:8-19`）；
- `options` 没有任何 adapter 读取，所有 `show_options` 都是 `False`；
- `id` 同时充当实例 ID 和 adapter 类型，无法支持同类型多实例；
- `cfg.capabilities` 在运行时被忽略，实际使用的是类属性 `Provider.capabilities`。

本次确认的方向：

| 决策点 | 结论 |
|---|---|
| 多实例 | 后端采用 `type` / `id` 分离的多实例数据模型；v1 UI 默认每种类型一个实例，暂不暴露“添加第二个实例” |
| 差异配置 | 方案 B：每个供应商一个强类型 Pydantic options 模型 + 声明式 FieldSpec + 一个动态表单渲染器 |
| per-request options | v1 不做，只在设计中预留 |
| advanced JSON | 仅作为高级折叠项，保存前必须按模型校验；不作为主交互 |
| secrets | v1 仅支持 Key 池；FieldSpec 的 `secret` 类型预留，暂不开放任意 secret 字段 |
| 字段范围 | 每个供应商只做一组高价值字段，其余进入 deferred 清单 |

核心原则：

> 协议差异留在 adapter；配置差异进强类型 schema；请求差异单独建模。  
> Pydantic options 模型是单一事实源，FieldSpec 是它的 UI 投影，避免“后端一份、前端一份”。

## 二、目标与非目标

### 目标

1. 现有六个供应商的配置可以平滑迁移，不破坏已有 `config.yaml` / `secrets.env`。
2. 管理端不再需要手写 JSON 才能配置供应商差异。
3. 每个供应商的字段有类型、默认值、枚举、帮助文本、分组和校验。
4. 支持 Jina 自建 `base_url`，并保留云端默认值。
5. 后端数据模型支持同类型多实例，为未来 Jina 云/自建、SearXNG HA、多 Exa 账号做准备。
6. 连接测试按 capability 执行，并检查单条结果的 `error`。

### 非目标

1. v1 不实现“添加第二个实例”的完整 UI。
2. v1 不做 per-request provider options。
3. v1 不做任意 secret 字段；密钥仍走 Key 池。
4. v1 不重写调度、合并、缓存、历史等引擎逻辑。
5. v1 不承诺覆盖供应商的全部 API 参数。

## 三、数据模型

### 3.1 ProviderConfig

```python
class ProviderConfig(BaseModel):
    id: str                  # 实例 ID，全局唯一，例如 "exa" / "exa-work"
    type: str                # adapter 类型，例如 "exa" / "jina"
    capabilities: list[str]  # 实例启用的能力，必须是 type 能力的子集
    enabled: bool = True
    weight: int = Field(default=10, ge=1, le=100)
    priority: int = Field(default=100, ge=1)
    max_results: int = Field(default=8, ge=1, le=50)
    base_url: str | None = None
    key_pool: KeyPoolConfig = KeyPoolConfig()
    options: dict[str, Any] = {}
```

迁移规则：

- 旧配置没有 `type` 时，加载阶段自动补 `type = id`。
- `id` 不可变；`type` 创建后不可变，改类型需删除重建。
- 新配置必须校验 `type` 存在于 `PROVIDER_CLASSES`。
- `id` 必须唯一；`type` 可以重复（为未来多实例预留）。
- `base_url` 保留字段名，语义由 `EndpointSpec` 决定。

### 3.2 ProviderSchema v0

```python
@dataclass(frozen=True)
class AuthSpec:
    mode: Literal["none", "bearer", "header", "query"] = "none"
    header_name: str | None = None
    query_param: str | None = None
    required: bool = False
    optional: bool = False
    key_prefix: str | None = None
    hint: str = ""


@dataclass(frozen=True)
class EndpointSpec:
    default: str | None = None
    overridable: bool = False
    required: bool = False
    label: str = "Base URL"
    placeholder: str = ""


@dataclass(frozen=True)
class FieldSpec:
    key: str
    label: str  # i18n key, e.g. "providers.fields.exa.search_type"
    type: Literal[
        "string", "text", "int", "float", "bool",
        "enum", "string_list", "secret",
    ]
    default: Any = None
    choices: tuple[str, ...] = ()
    required: bool = False
    capability: Literal["search", "extract"] | None = None
    group: str = "general"
    help: str = ""  # i18n key, e.g. "providers.fields.exa.search_type.help"
    placeholder: str = ""
    min: float | None = None
    max: float | None = None
    step: float | None = None
    advanced: bool = False
    visible_when: dict[str, Any] | None = None


@dataclass(frozen=True)
class TestSpec:
    capability: Literal["search", "extract"]
    query: str | None = None
    urls: tuple[str, ...] = ()
    max_chars: int = 200
    min_results: int = 0
    expect_content: bool = False


@dataclass(frozen=True)
class ProviderSchema:
    type: str
    name: str
    capabilities: tuple[str, ...]
    auth: AuthSpec = AuthSpec()
    endpoint: EndpointSpec = EndpointSpec()
    fields: tuple[FieldSpec, ...] = ()
    tests: tuple[TestSpec, ...] = ()
    key_pool_params: Literal["none", "rps", "full"] = "none"
    description_key: str | None = None
    docs_url: str | None = None
```

兼容属性（由上述字段派生，不再单独维护）：

| 旧字段 | 新来源 |
|---|---|
| `requires_key` | `auth.required` |
| `optional_key` | `auth.optional` |
| `requires_base_url` | `endpoint.required` |
| `key_prefix` | `auth.key_prefix` |
| `show_max_results` | `"search" in capabilities` |
| `show_options` | 废弃；由 `fields` 决定 |

这样可以消除当前 `REQUIRES_KEY` 与 `schema.requires_key`、类能力与 schema 能力之间的双份事实源。

## 四、供应商 v1 字段清单

### 4.1 Auth / Endpoint

| 供应商 | auth | Key 前缀 | endpoint 默认 | 可覆盖 | 必填 |
|---|---|---|---|---|---|
| ddg | none | — | — | — | — |
| searxng | none | — | — | 是 | 是 |
| exa | header `x-api-key` | — | `https://api.exa.ai` | 否 | — |
| tavily | bearer | `tvly-` | `https://api.tavily.com` | 否 | — |
| jina | bearer，可选 | `jina_` | `https://r.jina.ai/` | 是 | 否 |
| trafilatura | none | — | — | — | — |

### 4.2 Fields

| 供应商 | key | 类型 | 默认值 | capability | group | 备注 |
|---|---|---|---|---|---|---|
| ddg | `region` | string | `null` | search | search | 如 `us-en`、`cn-zh`、`wt-wt` |
| ddg | `safesearch` | enum | `moderate` | search | search | `on` / `moderate` / `off` |
| ddg | `timelimit` | enum | `""` | search | search | `""` / `d` / `w` / `m` / `y` |
| ddg | `backend` | string | `null` | search | advanced | 高级，库版本相关 |
| searxng | `categories` | string_list | `["general"]` | search | search | 如 `general,news` |
| searxng | `language` | string | `"all"` | search | search | SearXNG 语言代码 |
| searxng | `safesearch` | enum | `1` | search | search | `0` / `1` / `2` |
| searxng | `time_range` | enum | `""` | search | search | `day` / `week` / `month` / `year` |
| searxng | `engines` | string_list | `[]` | search | advanced | 空 = 使用实例默认引擎 |
| exa | `search_type` | enum | `auto` | search | search | `auto` / `lite` / `deep` |
| exa | `category` | string | `null` | search | search | `company` / `people` / `publication` / `news` 等 |
| exa | `include_domains` | string_list | `[]` | search | filters | — |
| exa | `exclude_domains` | string_list | `[]` | search | filters | — |
| exa | `start_published_date` | string | `null` | search | filters | 高级，ISO 日期 |
| exa | `end_published_date` | string | `null` | search | filters | 高级，ISO 日期 |
| exa | `include_text` | bool | `true` | — | content | search 与 extract 共用 |
| exa | `include_highlights` | bool | `false` | — | content | search 与 extract 共用 |
| exa | `include_summary` | bool | `false` | — | content | search 与 extract 共用 |
| tavily | `search_depth` | enum | `basic` | search | search | `basic` / `advanced` |
| tavily | `topic` | enum | `general` | search | search | `general` / `news` / `finance` |
| tavily | `include_domains` | string_list | `[]` | search | filters | — |
| tavily | `exclude_domains` | string_list | `[]` | search | filters | — |
| tavily | `include_answer` | bool | `false` | search | content | — |
| tavily | `include_raw_content` | bool | `false` | search | content | — |
| tavily | `days` | int | `null` | search | filters | 高级，仅 news 有意义 |
| tavily | `extract_depth` | enum | `basic` | extract | extract | `basic` / `advanced` |
| tavily | `include_images` | bool | `false` | extract | extract | — |
| jina | `target_selector` | string | `null` | extract | extract | CSS selector |
| jina | `wait_for_selector` | string | `null` | extract | extract | CSS selector |
| jina | `timeout_s` | int | `null` | extract | advanced | 1–120 秒 |
| jina | `no_cache` | bool | `false` | extract | advanced | — |
| trafilatura | `favor_precision` | bool | `false` | extract | extract | — |
| trafilatura | `favor_recall` | bool | `false` | extract | extract | — |
| trafilatura | `include_comments` | bool | `true` | extract | extract | — |
| trafilatura | `include_tables` | bool | `true` | extract | extract | — |
| trafilatura | `deduplicate` | bool | `false` | extract | advanced | — |
| trafilatura | `target_language` | string | `null` | extract | advanced | 如 `zh` |

说明：

- 输出格式是请求级参数（`fmt`），不做实例级默认：fanout 时多个供应商返回不同格式会造成合并结果不一致。
- 字段名和默认值在实现前需按各供应商当前 API/库版本再核对一次。
- `secret` 类型 v1 不使用，仅预留。

### 4.3 Deferred 字段

不在 v1 实现，避免范围膨胀：

- Exa：`additionalQueries`、`moderation`、`userLocation`、`maxAgeHours`、`subpages`、`context`。
- Tavily：`time_range`、`chunks_per_source`、`auto_parameters`、`country`。
- Jina：proxy、cookies、screenshot、engine、token budget。
- SearXNG：认证头、proxy、实例级 engine 配置。
- DDG：proxy、backend 细粒度参数。
- Trafilatura：`prune_xpath`、`include_images`、`include_links`、`include_formatting`、metadata。

## 五、Options 校验

每个供应商一个 Pydantic 模型，例如：

```python
class ExaOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    search_type: Literal["auto", "lite", "deep"] = "auto"
    category: str | None = None
    include_domains: list[str] = []
    exclude_domains: list[str] = []
    start_published_date: str | None = None
    end_published_date: str | None = None
    include_text: bool = True
    include_highlights: bool = False
    include_summary: bool = False
```

规则：

1. 保存时用 `Model.model_validate(options)` 校验；未知字段直接 400。
2. 加载时校验失败：记录 warning，将该实例标记为 `invalid_config`，不进入运行注册表。
3. 缺失字段使用模型默认值，保证旧配置兼容。
4. 后续如需要版本迁移，再增加 `options_version`；v1 不需要。
5. `options` 仍存 `config.yaml`；v1 不允许在其中放密钥。

## 六、测试规格（TestSpec）

| 供应商 | search 测试 | extract 测试 | 成功条件 |
|---|---|---|---|
| ddg | 查询 `searchhub connection test` | — | 无异常；允许 0 条结果 |
| searxng | 同上 | — | 无异常；允许 0 条结果 |
| exa | 同上 | `https://example.com` | extract 需 `error is None` 且 content 非空 |
| tavily | 同上 | `https://example.com` | 同上 |
| jina | — | `https://example.com` | 同上 |
| trafilatura | — | `https://example.com` | 同上 |

实现要求：

- 每个 capability 单独测试、单独记录状态；不再共用一个 `provider_tests[id]` 槽位。
- extract 测试必须检查 `ExtractItem.error`，不能只看列表长度。
- 真实调用记录与手动测试分开存储，避免“最近一次调用”覆盖“连接测试”。

## 七、迁移清单

### 7.1 配置与模型

- [ ] `ProviderConfig` 增加 `type`。
- [ ] 加载迁移：缺少 `type` 时补 `type = id`。
- [ ] 校验 `type` 已知、`id` 唯一、`type` 不可变。
- [ ] 为六个供应商增加 Pydantic options 模型。
- [ ] 保存时校验 options；加载失败标记 `invalid_config`。
- [ ] 增加 `invalid_config` 状态到管理端状态映射。

### 7.2 注册表与运行时

- [ ] `build_registry` 使用 `pc.type` 查 `PROVIDER_CLASSES`，`pc.id` 作为实例 ID。
- [ ] `Provider.supports` 使用实例 `cfg.capabilities`，不再使用类属性。
- [ ] `registry_for_capability` 使用实例能力。
- [ ] `provider_status` 返回实例能力，并附带 `type`。
- [ ] Key 池仍按实例 `id` 前缀读取；Key 格式校验按 `type` 的 schema 执行。
- [ ] 同类型多实例在 fanout 下会同时被调用；文档中明确这一行为，必要时增加“同类型只选一个”的后续策略。

### 7.3 管理 API

- [ ] create/update/test/auto-retest/status 全部按 `type` 取 schema。
- [ ] `POST /api/admin/providers` 校验 `type` 与 `id` 的关系。
- [ ] `POST /api/admin/providers/{id}/test` 按 capability 测试；支持指定 capability。
- [ ] `POST /api/admin/providers/test` 支持 draft 配置的 type/options 校验。
- [ ] `/v1/providers` 返回 `id`、`type`、实例 capabilities。

### 7.4 前端

- [ ] 供应商目录按 `type` 展示；已配置实例按 `id` 展示。
- [ ] 新建流程：选择类型 → 默认 `id = type` → 填写动态字段。
- [ ] 详情页：按 FieldSpec 分组渲染；支持 enum、string_list、bool、int、float、secret 占位。
- [ ] `endpoint.overridable` 为真时显示 Base URL；`endpoint.required` 为真时必填。
- [ ] Key 池按实例显示；`auth.required/optional` 决定是否显示。
- [ ] 测试按钮按 capability 分别执行，展示 item 级错误。
- [ ] 展示供应商描述、文档链接、字段帮助。
- [ ] 多实例：v1 不提供“添加第二个实例”按钮；若配置中已存在多个实例，按类型分组展示。
- [ ] 保留高级 JSON 折叠项时，必须按模型校验，不能静默保存未知字段。

### 7.5 缓存

- [ ] 搜索缓存键加入配置版本或 provider/options 哈希，避免配置变更后命中旧结果。
- [ ] 提取缓存键加入 options 哈希；当前 extract 缓存键不包含 provider/options（`cache_keys.py:14-15`）。
- [ ] 明确多实例下 `providers=all` 的缓存语义。

### 7.6 测试与文档

- [ ] schema 测试：auth/endpoint/fields/tests 派生属性。
- [ ] registry 测试：type/id 分离、实例能力、多实例。
- [ ] admin 测试：未知 type、重复 id、options 校验、按 capability 测试。
- [ ] 前端测试：FieldSpec 渲染、条件显示、错误提示。
- [ ] README 更新供应商表、Jina 自建、多实例说明。
- [ ] 发布说明包含配置迁移说明。

## 八、验收标准

1. 旧 `config.yaml` 无需手工修改即可加载，所有原有供应商继续工作。
2. 六个供应商的 v1 字段均可在 UI 中配置，不再需要 raw JSON。
3. Exa/Tavily 的 search + extract 可以分别测试；Jina/Trafilatura 的 extract 测试能识别 item 级错误。
4. Jina 可以通过 `base_url` 指向自建 Reader。
5. 后端可以通过配置/API 创建同类型第二个实例并正常运行；UI 暂不暴露该入口。
6. 关闭某实例的 `extract` 能力后，运行时不再把 extract 请求路由给它。
7. 未知 options 字段保存时被拒绝，不会静默忽略。

## 九、实施阶段（仅 outline，不是详细计划）

1. **阶段 1：配置与 schema 基础**  
   `type` 字段、迁移、ProviderSchema/FieldSpec、options 模型；不改变现有 UI 行为。
2. **阶段 2：运行时正确性**  
   注册表按 type、实例 capabilities、Key 校验、按 capability 测试。
3. **阶段 3：Exa 试点**  
   Exa 的 options + 动态表单渲染器 + 测试规格；验证方案 B。
4. **阶段 4：其余供应商**  
   Tavily、DDG、SearXNG、Jina、Trafilatura；Jina base_url。
5. **阶段 5：文档与可选多实例 UI**  
   README、迁移说明；按需开放“添加第二个实例”。

## 十、风险与待确认

1. 各供应商字段名/默认值可能随 API 版本变化，实施前需核对官方文档。
2. 多实例在 fanout 下会重复调用同类型实例，可能增加成本和延迟；v1 通过“UI 默认单实例”规避，后续需要路由策略。
3. 缓存键改造会影响命中率，需要单独评估。
4. v1 不支持 per-request options，调用方只能使用实例默认值。
5. v1 不支持任意 secret 字段，非 Key 类凭据（如 SearXNG Basic Auth）暂不覆盖。
6. `max_results` 仍是公共字段；如果未来需要按 capability 设置不同默认值，再单独设计。

## 十一、本次默认取舍（可被否决）

- 多实例：后端模型支持，v1 UI 单实例。
- per-request options：v1 不做。
- advanced JSON：保留但校验，不作为主入口。
- secrets：v1 仅 Key 池。
- 字段范围：按上表执行，deferred 字段不进 v1。
