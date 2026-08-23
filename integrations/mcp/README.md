# SearchHub MCP 接入

MCP（Model Context Protocol）接入，让 AI Agent（opencode / claude / cursor 等）直接调用 SearchHub 的搜索与提取能力。提供两个工具，返回单一 JSON 字符串（成功时形状与 REST `/v1` 的 data 部分一致，不含 `success` 标志——客户端按形状或错误字段探测）：

- `web_search(query, limit?, providers?, strategy?)`：网页搜索
- `web_extract(urls, format?, max_chars?)`：网页内容提取

## 鉴权与验证

- 远程（http）方式需要调用方 Token（管理后台「调用方 Token」页创建），经 `Authorization: Bearer <token>` 携带；缺失或无效返回 401
- 本地（stdio）方式本机直连，无需 Token

> Docker 部署时 stdio 模式在宿主机执行：需要宿主机有 Python 与 searchhub 包；否则用远程方式指向 `http://<NAS-IP>:8000/mcp`。

所有调用会记录在管理后台「历史查询」页。

## opencode

远程（http，内网部署）——写入项目根目录 `opencode.json`（或全局 `~/.config/opencode/opencode.json`）：

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "searchhub": {
      "type": "remote",
      "url": "http://<host>:8000/mcp",
      "enabled": true,
      "headers": { "Authorization": "Bearer <token>" }
    }
  }
}
```

本地（stdio，本机运行）——同样写入上述 `opencode.json`：

```json
{
  "mcp": {
    "searchhub": {
      "type": "local",
      "command": ["python", "-m", "searchhub.mcp"],
      "enabled": true,
      "environment": { "SEARCHHUB_DATA": "/path/to/searchhub/data" }
    }
  }
}
```

## Claude Code

```bash
claude mcp add searchhub --transport http http://<host>:8000/mcp --header "Authorization: Bearer <token>"
```

或写入 `.mcp.json`（项目级，`mcpServers` 字段）：

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

## Cursor

Settings → MCP → 添加，或 `.cursor/mcp.json`（与 Claude 同款 `mcpServers` 结构）：

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

## Codex

`~/.codex/config.toml`：

```toml
[mcp_servers.searchhub]
command = "python"
args = ["-m", "searchhub.mcp"]
env = { SEARCHHUB_DATA = "/path/to/searchhub/data" }
```

## Gemini CLI

在设置中加入 `mcpServers`（与 Claude 同款结构）：

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


## 引导 Agent 主动使用（可选）

配置好 MCP 后，在对应 agent 的**说明文件**中加入一段指引，可以让 agent 在需要最新信息时主动调用工具（而不是只依赖内置知识）。各 agent 的说明文件：

| Agent | 文件 |
|---|---|
| opencode / Codex | `AGENTS.md`（项目根或全局） |
| Claude Code | `CLAUDE.md` |
| Cursor | `.cursor/rules/*.mdc` |
| Gemini CLI | `GEMINI.md` |

可粘贴的通用片段：

```markdown
## Web 搜索与提取

需要最新信息、实时数据或网页内容时，使用 MCP 工具（经 SearchHub 聚合，无需直接访问网页）：

- `web_search(query, limit?)`：网页搜索，返回 `{success, data: {web: [{title, url, description}]}}` 形状的 JSON
- `web_extract(urls, format?)`：网页内容提取，返回 JSON 数组（每项含 url/title/content）

优先使用这两个工具而非模型内置知识；搜索前不确定时先用 `web_search` 验证或补充信息。
```

各 agent 会按自身约定读取对应文件并遵循其中对工具的使用指引。
