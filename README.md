# SearchHub

自托管统一 Web 搜索 / 网页提取聚合服务。一个服务聚合多家搜索与提取供应商（exa / tavily / ddg / searxng / jina / trafilatura ...），统一管理 API Key 与多 Key 轮换，为你的 AI Agent 提供稳定可靠的搜索与网页提取能力。

- **多供应商聚合**：并发 / 轮换 / 主备三种调度策略，失败自动剔除、按质量权重合并排序
- **多 Key 管理**：每个云供应商支持多个 Key 自动轮换、限速与故障冷却
- **网页提取**：统一提取接口（markdown / 纯文本），本地或云端供应商可选
- **全量 UI 管理**：供应商、Key、策略、缓存、调用方 Token、历史与统计全部在管理后台完成，无需编辑配置文件；支持中英文与明暗主题
- **Agent 接入**：REST API、MCP、hermes 插件、dsh 插件、Agent Skill、工具安装包
- **一键部署**：Docker Compose，NAS 友好，零环境依赖（无需安装 Python / npm）

## 快速部署（Docker）

适合 NAS 等自托管场景。前提：已安装 Docker 与 Docker Compose v2。

```bash
git clone https://github.com/RedDous/SearchHub.git && cd SearchHub
docker compose up -d --build        # 首次构建含前端编译，约几分钟
```

打开 `http://<NAS-IP>:8000`：

1. 首次登录默认账号 `admin / admin`（若在 `.env` 设置了 `ADMIN_PASSWORD` 则为该值），登录后系统会强制要求修改密码
2. 在管理后台按目录添加供应商（点选类型 → 专属表单）并启用
3. 在「调用方 Token」页创建 Token，供 REST / MCP / Agent 接入使用

**可选 sidecar**（自建 SearXNG 聚合搜索与 crawl4ai 网页提取副车，按需启用）：

```bash
docker compose --profile sidecars up -d
```

然后在管理后台添加供应商：searxng → base_url `http://searxng:8080`；crawl4ai → base_url `http://crawl4ai:11235`。

**数据与备份**：全部数据位于 `./data/`（config.yaml、secrets.env、history.db、cache.db、session_secret）。备份 = 拷贝整个目录；恢复 = 拷贝回去后重启服务。

**更新**：`git pull && docker compose up -d --build`

**说明**：

- `.env` 完全可选——不创建也能零配置启动（首次密码即默认 admin）；如密码含 `$` 请用 `$$` 转义
- 前端已内置镜像，无需在 NAS 上单独构建
- 镜像内以 root 运行（家用场景简化；如需非 root 可在 compose 加 `user:`）

## 本地开发

```bash
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
SEARCHHUB_DATA=./data .venv/bin/python -m searchhub    # 后端，端口 8000
```

管理后台前端（`frontend/`，Vue3 SPA）：

```bash
cd frontend && npm install
npm run dev         # Vite dev server（5173），代理 /api /v1 /healthz 到 8000
npm run build       # 产物 frontend/dist 由后端自动托管
```

测试：后端 `.venv/bin/pytest`；前端 `cd frontend && npm test`。

## 使用

### 管理后台

浏览器打开 `http://<host>:8000` 登录后：

| 页面 | 功能 |
|---|---|
| 仪表盘 | 24h 请求量、成功率、缓存命中率、趋势图、供应商状态 |
| 供应商 | **目录式配置**：点选供应商类型进入其专属表单（能力、base_url、限速参数按类型显示），连接测试、Key 池增删（掩码显示、多 Key 自动轮换） |
| 策略与缓存 | 默认调度模式（fanout 并发 / rotation 轮换 / primary_fallback 主备）、超时、缓存 TTL、历史保留期与查询脱敏 |
| 调用方 Token | 创建 / 吊销 Bearer Token（明文仅创建时显示一次） |
| 历史查询 | 全部搜索 / 提取请求记录，按能力 / 供应商 / Token / 时间筛选，展开查看详情 |
| 系统设置 | 修改密码、语言（中文 / English）、明暗主题、自定义壁纸 |

所有配置写操作原子写入 `data/config.yaml` / `data/secrets.env` 并热重载（自动滚动备份 5 份），日常使用无需手工编辑文件。

### 配置文件（参考）

- `config.yaml`：供应商、策略、缓存、历史、管理员与调用方 Token（`auth.tokens[].token_hash` 为 sha256 哈希）
- `secrets.env`：供应商 API Key，格式 `{ID}_KEY_N`（如 `EXA_KEY_1=xxx`），权限 600

## 对外接口

### REST API

所有 `/v1/*` 需请求头 `Authorization: Bearer <token>`（Token 在管理后台创建）：

| 端点 | 说明 |
|---|---|
| `GET/POST /v1/search?q=...&limit=` | 聚合搜索 |
| `GET/POST /v1/extract?urls=...` | 网页提取（单 / 多 URL） |
| `GET /v1/providers` | 当前启用的供应商与能力 |
| `GET /healthz` / `GET /readyz` | 健康检查 |

响应为统一信封 `{"success": true, "data": ..., "meta": ...}`；失败为 `{"success": false, "error": "..."}`。`/v1/search` 的 `data.web[]` 包含 `title / url / description / position`。

### MCP

两个工具：`web_search(query, limit?, providers?, strategy?)`、`web_extract(urls, format?, max_chars?)`，返回单一 JSON 字符串（形状与 REST 的 data 部分一致）。

**streamable-http**（随主服务挂载于 `/mcp`，需 Token）：

```json
{
  "mcpServers": {
    "searchhub": {
      "url": "http://<host>:8000/mcp",
      "headers": { "Authorization": "Bearer <token>" }
    }
  }
}
```

**stdio**（本机直接运行，无需 Token）：

```bash
SEARCHHUB_DATA=./data .venv/bin/python -m searchhub.mcp
```

```json
{
  "mcpServers": {
    "searchhub": {
      "command": "python",
      "args": ["-m", "searchhub.mcp"],
      "env": { "SEARCHHUB_DATA": "/path/to/searchhub/data" }
    }
  }
}
```

## Agent 接入（integrations/）

| 接入方式 | 位置 | 适用 |
|---|---|---|
| hermes 插件 | `integrations/hermes/` | hermes-agent 原生后端，顶替内置 `web_search` / `web_extract` |
| dsh 插件 | `integrations/dsh/` | DeepSeek Harness `ctx.web` seam（search + fetch 双能力） |
| Agent Skill | `integrations/skill/` | opencode / Claude Code / Codex 等技能目录 |
| 工具安装包 | `integrations/tools/` | 自定义 harness 的 function-calling 定义，及 Claude Code / Codex / Cursor / OpenCode / Gemini CLI 安装片段 |

各目录内 README 含安装与配置步骤（Token 均在管理后台「调用方 Token」页创建）。

## 目录结构

```
src/            # 后端（FastAPI：聚合引擎、供应商适配器、管理 API、MCP）
frontend/       # 管理后台（Vue3 SPA）
integrations/   # Agent 接入件（hermes 插件 / dsh 插件 / skill / tools）
data/           # 运行时数据（config.yaml、secrets.env、*.db，部署时挂载卷）
```