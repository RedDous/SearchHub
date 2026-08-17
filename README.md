# SearchHub

自托管统一 Web 搜索 / 网页提取聚合服务（M1：核心引擎 + REST API）。

## 快速开始

```bash
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
SEARCHHUB_DATA=./data .venv/bin/python -m searchhub
```

首次启动自动生成 `data/config.yaml` 与 `data/secrets.env`。

## 配置示例

`data/secrets.env`（密钥，权限 600）：
```
EXA_KEY_1=xxx
TAVILY_KEY_1=yyy
```

`data/config.yaml` 添加供应商：
```yaml
providers:
  - id: exa
    capabilities: [search, extract]
    enabled: true
    weight: 10
  - id: ddg
    capabilities: [search]
    enabled: true
  - id: trafilatura
    capabilities: [extract]
    enabled: true
```

## API

所有 `/v1/*` 接口需 `Authorization: Bearer <token>`；token 以 sha256 哈希加入 config.yaml：

```yaml
auth:
  tokens:
    - name: my-agent
      token_hash: <sha256(token)>
```

- `GET /v1/search?q=...&limit=5` 或 `POST /v1/search {"q": ...}`
- `GET /v1/extract?urls=a,b` 或 `POST /v1/extract {"urls": [...]}`
- `GET /v1/providers`
- `GET /healthz` / `GET /readyz`

生成 token 哈希：`python -c "import hashlib; print(hashlib.sha256(b'YOUR_TOKEN').hexdigest())"`

## 管理后台（M2）

管理 API 位于 `/api/admin/*`（与公开 API 分离，使用独立管理员会话）：

- 登录：`POST /api/admin/login`（`{"username", "password"}`），会话存 httpOnly Cookie
- 首次启动：若 `config.yaml` 无密码哈希，使用环境变量 `ADMIN_PASSWORD`；未设置则默认 `admin/admin`（启动日志有警告，请尽快在 UI 改密）
- 功能：供应商 CRUD 与连接测试、Key 池增删（掩码显示）、策略/缓存/历史设置、调用方 Token 创建/吊销、历史查询、统计（summary + 每小时时序）、配置版本查看
- 所有写操作原子写入 `data/config.yaml`/`data/secrets.env` 并热重载，自动滚动备份 5 份
- 历史记录存 `data/history.db`，默认保留 30 天，后台每小时自动清理；`history.redact_queries: true` 可对 query 落盘前 sha1

## MCP Server（M3）

MCP（Model Context Protocol）接入，让 AI 客户端（opencode / claude / cursor 等）直接调用搜索与提取能力。提供两个工具，返回单一 JSON 字符串（成功时形状与 REST `/v1` 的 data 部分一致，不含 `success` 标志——客户端按形状或错误字段探测）：

- `web_search(query, limit=5, providers?, strategy?)`：网页搜索
- `web_extract(urls, format="markdown", max_chars=15000)`：网页内容提取

支持两种传输：

**stdio（本地 CLI，无需启动 HTTP 服务）**

```bash
SEARCHHUB_DATA=./data .venv/bin/python -m searchhub.mcp
```

MCP 客户端配置示例（stdio）：

```json
{
  "mcpServers": {
    "searchhub": {
      "command": "python",
      "args": ["-m", "searchhub.mcp"],
      "env": {
        "SEARCHHUB_DATA": "/path/to/searchhub/data"
      }
    }
  }
}
```

**streamable-http（经主服务挂载于 `/mcp`）**

随主服务一起启动，无需额外进程。MCP 客户端配置示例：

```json
{
  "mcpServers": {
    "searchhub": {
      "url": "http://127.0.0.1:8000/mcp",
      "headers": {
        "Authorization": "Bearer <token>"
      }
    }
  }
}
```

### 鉴权

与 REST `/v1` 同一套调用方 Token：token 在管理后台「调用方 Token」页创建（或 `POST /api/admin/tokens`）。streamable-http 通过 `Authorization: Bearer <token>` 请求头携带；stdio 模式在本地直接调用，无需 token。请求头缺失或 token 无效返回 `401`。

### 验证

```bash
# stdio 冒烟：正常时会持续等待标准输入，3 秒后被 timeout 终止（exit=124）
timeout 3 .venv/bin/python -m searchhub.mcp; echo "exit=$?"
```

随后在任意 MCP 客户端（opencode / claude / cursor）中按上面的配置连接，调用 `web_search` / `web_extract` 即可。

## 测试

```bash
.venv/bin/pytest
```

## 前端（M2B）

管理后台为 Vue3 SPA，位于 `frontend/`。

开发：启动后端（`python -m searchhub`，端口 8000），然后
```bash
cd frontend && npm install && npm run dev
```
Vite dev server（默认 5173）代理 `/api`、`/v1`、`/healthz` 到 `127.0.0.1:8000`，同源 Cookie 会话直接可用。

构建：
```bash
cd frontend && npm run build
```
产物 `frontend/dist` 由后端自动托管（`SEARCHHUB_WEB_DIST` 可覆盖路径；目录不存在则不挂载，仅 API）。SPA fallback 仅作用于非 API 路径。

测试：`cd frontend && npm test`（vitest 单测）；后端回归 `pytest`。
