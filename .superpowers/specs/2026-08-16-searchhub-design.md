# SearchHub 设计文档

> 日期：2026-08-16
> 状态：已批准（草稿评审后定稿）

## 一、项目概述

SearchHub 是一个自托管的**统一 Web 搜索与网页提取聚合服务**，部署于用户 NAS（Docker 单容器）。它为 AI agent 提供稳定的 `web_search` / `web_extract` 能力，聚合多家搜索/提取供应商，统一管理 API 密钥（多 Key 池、轮换、并发、故障转移），并以多种方式暴露给 agent 生态。

核心价值：
- 一个 NAS 服务，统一接入云供应商（exa、tavily 等）与本地部署（SearXNG、ddg、crawl4ai 等）
- 多 Key 打散防频控/风控；多供应商并发聚合提升质量与容错
- 密钥与配置集中管理，全量 UI 可视化配置，用户无需触碰配置文件
- 多形态接入：REST API、MCP server、hermes 插件、dsh 插件、agent skill、agent tool 安装包

### 技术决策摘要

| 决策点 | 结论 |
|---|---|
| 后端技术栈 | Python + FastAPI |
| 管理 UI | 独立前端（Vue3 SPA）+ 后端托管静态文件，单容器 |
| 配置存储 | `config.yaml`（非敏感）+ `secrets.env`（密钥，明文+防护），UI 全量读写，热重载 |
| 数据存储 | SQLite（WAL 模式），存储层薄抽象，不接 MySQL/Redis |
| 密钥策略 | 明文存储 + 权限 600 + UI 掩码 + 日志脱敏；备份加密写进文档 |
| 接口优先级 | 一期：REST + MCP；二期：hermes 插件、dsh 插件、skill、agent tool 安装包 |
| 供应商 v1 | 搜索：exa、tavily、ddg、searxng；提取：jina reader、trafilatura |
| 服务鉴权 | 强制 API Token（调用方），UI 单独 JWT 管理员登录 |
| 默认调度 | fanout 并发全部启用供应商，可切 rotation / primary_fallback |
| 缓存 | SQLite 可配置 TTL（搜索 10min、提取 24h），支持绕过/刷新 |

## 二、整体架构

```
┌────────────────────────── SearchHub 单容器 ──────────────────────────┐
│  FastAPI 单进程                                                       │
│   ├─ 公共 REST API   /v1/search /v1/extract（API Token 鉴权）          │
│   ├─ MCP Server      FastMCP 挂载 /mcp（streamable-http）              │
│   │                   + CLI `python -m searchhub.mcp` 可跑 stdio      │
│   ├─ 管理 API        /api/*（JWT 登录，单管理员）                       │
│   ├─ 静态 UI         Vue3 SPA（构建产物，后端托管）                     │
│   ├─ 聚合引擎                                                          │
│   │   ├─ 调度策略: fanout(默认) / rotation / primary_fallback          │
│   │   ├─ 每供应商 Key 池: 轮转 + 冷却 + 并发限制 + 限速                  │
│   │   ├─ 合并/去重/排序: 质量权重                                       │
│   │   └─ 故障转移: 失败剔除、全部失败才报错                               │
│   ├─ 供应商 Adapter（可插拔注册表）                                     │
│   │   └─ 搜索: exa / tavily / ddg / searxng(JSON API)                 │
│   │   └─ 提取: jina reader / trafilatura(本地库)                        │
│   ├─ 缓存与历史 (SQLite: search_cache / extract_cache / request_log)   │
│   └─ 配置服务 (config.yaml + secrets.env, 热重载, UI 读写)              │
└───────────────────────────────────────────────────────────────────────┘
   ▲ 消费方: hermes 插件 / dsh 插件 / agent skill / agent tool / MCP 客户端 / curl
   ▲ 外部: SearXNG 实例、crawl4ai-server（compose profile 可选拉起，二期）
```

选型：单进程单体（方案 A）。MCP 与 REST 共享引擎/缓存/配置；MCP 同时提供 streamable-http 挂载与 stdio CLI 两种运行方式，兼顾远程 agent 与本机 agent。

### 供应商能力模型

Adapter 采用能力声明模型（与 hermes `supports_search/supports_extract` 同构）：

| 供应商 | 能力 | 类型 | Key | v1 |
|---|---|---|---|---|
| exa | search + extract | 云 API（`/search`、`/contents`） | 需要 | ✅ |
| tavily | search + extract | 云 API（`/search`、`/extract`） | 需要 | ✅ |
| ddg | search | 本地库（duckduckgo-search） | 免 key | ✅ |
| searxng | search | 本地 HTTP（JSON API） | 免 key（需 URL） | ✅ |
| jina reader | extract | 云免费（r.jina.ai） | 可选 | ✅ |
| trafilatura | extract | 本地库（随包自带） | 免 key | ✅ |
| firecrawl | extract | 云/自建 | 需要 | 二期 |
| crawl4ai | extract | 本地自建（crawl4ai-server） | 免 key | 二期 |
| brave / serper / bing / Google CSE | search | 云 API | 需要 | 二期 |

双能力供应商的 Key 池对两个能力共享。

## 三、聚合引擎

### 统一数据模型

```
SearchItem   {title, url, description, position, provider, score, published_at?}
ExtractItem  {url, title, content, raw_content, metadata, provider, error?}
```

各供应商响应先归一化为上述模型，再进入策略/合并管线。

### Key 池（每供应商一组）

- 每个 key 独立状态：`可用 / 冷却中（错误或 429 后 n 秒）/ 超并发上限`
- 取 key：轮转（round-robin，跳过冷却中的）→ 全部冷却则取最早恢复的
- 每 key 可配：`max_concurrency`（信号量）、`rps_limit`（滑动窗口）、`cooldown_after_error`
- 429/401/432 等状态码自动标记冷却，冷却期可配置（默认 60s，429 优先按 `Retry-After`）
- 密钥存储在 `secrets.env`，命名约定 `PROVIDER_ID_KEY_N`（如 `EXA_KEY_1`），映射到供应商

### 调度策略（每请求可选，默认 fanout）

| 模式 | 行为 | 适用 |
|---|---|---|
| `fanout`（默认） | 全部启用供应商并发调用，各限 `max_results`，合并去重，按质量权重加权排序 | 质量优先 |
| `rotation` | 只挑一个供应商（内部先 key 轮转再供应商轮转），失败自动换下一家 | 省额度、防频控 |
| `primary_fallback` | 按优先级列表顺序，成功即返回；单个供应商内部也按 key 轮转 | 可控、低延迟 |

- 全局请求级 `timeout`（默认 15s）；fanout 下单供应商超时用 `asyncio.wait` 收集先完成的，不拖累整体
- 每供应商可配 `weight`（质量权重，fanout 排序用）与 `priority`（primary_fallback 顺序用）

### 合并与排序（fanout）

- 按规范化 URL 去重（去 `#fragment`、`utm_*`、尾部斜杠、http/https 统一）
- 去重后保留质量权重最高来源的条目；同 URL 的 title/description 择优合并
- 排序：`score = 供应商权重 × 位置衰减`，按 `limit` 截断
- 供应商零结果不算失败；**全部**失败（含零启用供应商）才整体报错，错误信息带每供应商明细

### 失败形状（与 hermes 契约一致）

```json
{"success": false, "error": "..."}
```

- 单 URL 提取失败：结果数组中该项带 `error` 字段，其余正常返回
- 供应商级错误记入 stats 并在 UI 暴露

### 缓存（SQLite）

- 表：`search_cache` / `extract_cache`
- 默认 TTL：搜索 600s、提取 86400s；UI 可开关可调
- 请求带 `cache=false` 强制绕过、`refresh=true` 强制刷新
- 提取缓存 key = 规范化 URL + 参数指纹

### 并发与限流（出站）

- 每 key 信号量限并发；每供应商令牌桶全局限速（防止把自己打挂）
- 入站代理层限流在管理面配置（二期细化）

## 四、对外接入层

### 鉴权

- 所有公共端点（REST + MCP）要求 `Authorization: Bearer <token>`
- token 由 UI 创建/吊销，以哈希形式存于配置（`token_hash`），支持备注
- UI 管理员会话独立（JWT），与调用方 token 体系分离

### REST API

响应形状与 hermes 契约位对位一致，插件层纯透传。

`GET/POST /v1/search`
```jsonc
// 参数: q, limit(默认5), providers(逗号分隔,默认全部), strategy(可选覆盖),
//       cache, timeout, 以及透传给供应商的扩展参数
{"success": true, "data": {"web": [
  {"title": "...", "url": "...", "description": "...", "position": 0,
   "provider": "exa", "score": 0.9}
]}, "meta": {"took_ms": 320, "cached": false, "provider_stats": {...}}}
```
> hermes 只读 `data.web[].title/url/description/position`；`provider/score` 为附加字段，向后兼容。

`GET/POST /v1/extract`
```jsonc
// 参数: url 或 urls[](单/多), format(text|markdown,默认markdown), include_raw(默认true),
//       max_chars(默认15000), cache, strategy
{"success": true, "data": [
  {"url": "...", "title": "...", "content": "...", "raw_content": "...",
   "metadata": {}, "provider": "trafilatura"}
], "meta": {...}}
```

辅助端点：`GET /v1/providers`（能力探测：各供应商 search/extract 支持情况 + 延迟统计）、`GET /healthz`、`GET /readyz`。

### MCP Server

- FastMCP 挂载 `/mcp`（streamable-http 传输），与 REST 同进程共享引擎
- 工具：`web_search(query, limit?, providers?, strategy?)`、`web_extract(urls, format?, max_chars?)`
- 工具返回单一 JSON 字符串（形状同 REST data 部分）
- token 经 MCP 请求头 `Authorization` 传入
- CLI `python -m searchhub.mcp` 以 stdio 运行，供本机 agent 配置

### 二期接入形态（均为薄壳）

1. **hermes 插件**：`~/.hermes/plugins/web/searchhub/`，`plugin.yaml` + `provider.py`，`supports_extract() -> True`，httpx 透传 REST，`is_available()` 只查配置不联网
2. **dsh 插件**：npm 包（Cordis 插件），注册 search/extract 工具调 REST；dsh 处于 dev preview 迭代期，实现时按当时接口核对
3. **agent skill**：`SKILL.md` 描述 REST 用法 + 示例 curl
4. **agent tool 安装包**：`integrations/tools/` 目录，为 Claude Code / Codex / Cursor / OpenCode / Gemini CLI 等各提供其格式的 tool 定义（JSON schema）+ 安装脚本/说明；实现时逐一核对各 harness 当前 tool 注册格式（快速演进中），原生不支持自定义 tool 的 harness 回退给 MCP 配置片段

## 五、配置模型与管理面

### 配置文件（`/data` 卷，UI 全量读写、热重载）

`config.yaml`（非敏感）
```yaml
server: {port, public_base_url}
admin: {username, session_ttl_hours}
auth:
  tokens: [{id, name, token_hash, created_at, revoked}]
strategy:
  default_mode: fanout
  timeout_s: 15
cache: {enabled, search_ttl_s: 600, extract_ttl_s: 86400}
history: {retention_days: 30, redact_queries: false}
providers:
  - id: exa
    capabilities: [search, extract]
    enabled: true
    weight: 10
    priority: 1
    max_results: 8
    key_pool: {max_concurrency: 2, rps_limit: 10, cooldown_s: 60}
    options: {}          # 供应商特有参数
  - id: searxng
    capabilities: [search]
    base_url: http://searxng:8080
    ...
```

`secrets.env`（敏感，权限 600，支持 docker secret）
```
EXA_KEY_1=..., EXA_KEY_2=...
TAVILY_KEY_1=...
```

### 密钥安全（默认方案：明文 + 三道防护）

1. `secrets.env` 权限 600、位于 `/data` 卷、`.gitignore` 排除、不在任何 HTTP 静态路径下
2. UI 写入后即掩码：保存后仅显示掩码（`tvly-****4f2a`），支持复制/删除/替换，不回显完整值（防肩窥、防管理 API 响应/日志泄露）
3. 密钥不出现在任何日志、任何 API 响应、错误信息中（统一 redaction）

明文的好处：可备份、可迁移、可恢复。二期可选做主密钥 AES-GCM 加密落盘（默认关，主密钥丢失=全部密钥不可恢复）。

### 管理 API（`/api/*`，JWT 会话）

- 认证：登录/登出/改密
- 供应商：增删改查、启停、权重/优先级/参数、**连接测试**（实时验证）
- 供应商详情内管理 Key 池：增删 key、实时状态（冷却中/并发数/近 1h 成功率与错误分布）
- 策略与缓存：模式、超时、TTL 可视化编辑
- 调用方 token：创建/吊销
- 统计：近 24h 请求量、缓存命中率、各供应商成功率/延迟曲线、失败原因 Top（ECharts）
- 日志：请求级查看，可过滤，不落盘敏感参数

### 配置一致性

所有写操作走管理 API → 校验（YAML 语法、key 引用完整性）→ 原子写文件 → 热重载生效；写前自动备份（滚动 5 份 `config.yaml.bak`）。UI 显示当前配置版本与最近变更时间。

### 管理 UI（Vue3 SPA，静态托管）

- **主题**：默认亮色，明暗切换（本地记忆），中英文切换（i18n，默认中文），自定义背景壁纸（预设 + 用户上传，上传存 `/data/uploads`，仅 UI 装饰用）
- **页面**：仪表盘（统计）｜ 供应商（列表 + 详情，详情内含 API Key 管理区块）｜ 策略与缓存 ｜ 调用方 Token ｜ 历史查询 ｜ 日志 ｜ 系统设置（管理员密码、时区、语言）
- **历史查询页**：所有历史请求持久化（SQLite `request_log`），字段含时间、能力、query/urls、参数、实际供应商组合、缓存命中、耗时、结果数、调用方 token、响应预览（截断）；支持按时间范围/能力/供应商/token 筛选，点击展开详情；保留期可配（默认 30 天自动清理）；可选查询内容脱敏（默认关）
- 风格参考 Uptime Kuma / n8n；暗色主题 + 响应式

## 六、部署、测试与里程碑

### 部署

- 多阶段 Dockerfile：前端构建（node）→ Python 运行镜像（slim），单容器
- `docker-compose.yml`：服务 + `/data` 卷（config.yaml、secrets.env、SQLite）；searxng / crawl4ai 等外部服务由用户自行部署，经 base_url 接入
- 环境变量覆盖：`ADMIN_PASSWORD`（首次启动设密码）、`PORT`、`PUBLIC_BASE_URL`

### 测试

- 引擎单测：key 池轮转/冷却、三种策略、去重排序、缓存命中
- Adapter 测试：httpx mock（respx）模拟各供应商响应与 429/5xx，不真实调云
- API 集成测试：鉴权、契约形状校验
- 前端：构建通过 + 关键流程手动验收清单

### 里程碑

| 里程碑 | 内容 |
|---|---|
| M1 核心引擎 + REST | 供应商注册表、Key 池、三种策略、缓存、REST API、config/secrets 服务、单元+集成测试 |
| M2 管理面 | 管理 API + UI（供应商/Key/策略/Token/统计/日志/历史/设置/i18n/主题） |
| M3 MCP | streamable-http 挂载 + stdio CLI |
| M4 打包与消费方 | Docker/compose（拉镜像+源码双模式）、hermes 插件、dsh 插件、skill、agent tool 安装包、文档 |

二期后置：firecrawl/crawl4ai adapter、brave/serper 等更多供应商、入站限流细化、密钥加密落盘（默认关）。

## 七、参考项目

- SearXNG（搜索元引擎）、firecrawl、crawl4ai（提取/爬取）
- Tavily（search + extract API）、Exa（search + contents API）、Jina Reader（r.jina.ai）
- WSA（SearXNG 兼容聚合代理，用户自有基建）
- hermes-agent（消费方，契约见 `tmp/hermes-web-backend-spec.md`）
- deepseek-harness / dsh（消费方，Cordis 插件体系 + MCP 一等公民）
- UI 风格参考：Uptime Kuma、n8n
