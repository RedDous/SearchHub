# SearchHub Agent Tool 安装包

统一 OpenAI function-calling 风格的 tool JSON（`web_search.json` / `web_extract.json`）+ 各 agent 的安装片段。tool 名与 MCP 工具名一致（`web_search` / `web_extract`），REST 契约均为 `POST {SEARCHHUB_URL}/v1/search` / `/v1/extract`（Bearer token）。

## 通用（自定义 harness）

直接读取两个 JSON 文件注册工具，调用时：

```bash
curl -s "$SEARCHHUB_URL/v1/search" \
  -H "Authorization: Bearer $SEARCHHUB_TOKEN" \
  -G --data-urlencode "q=$query" --data-urlencode "limit=$limit"
```

响应（`{success, data, meta}`）原样透传给模型即可。

## Claude Code

```bash
claude mcp add searchhub --transport http http://<host>:8000/mcp \
  --header "Authorization: Bearer <token>"
```

或写入 `~/.claude.json` 的 `mcpServers` 配置。skill 安装见 [integrations/skill](../skill/searchhub-web/SKILL.md)。

## Codex

`~/.codex/config.toml` 增加 `mcp_servers`（stdio 或 http 均可）：

```toml
[mcp_servers.searchhub]
transport = "http"
url = "http://<host>:8000/mcp"
headers = { Authorization = "Bearer <token>" }
```

并将 [skill](../skill/searchhub-web/SKILL.md) 复制到 `~/.codex/skills/searchhub-web/`。

## Cursor

Settings → MCP → Add：

- URL：`http://<host>:8000/mcp`
- Header：`Authorization: Bearer <token>`

## OpenCode

`opencode.json` 的 `mcp` 段：

```json
{
  "mcp": {
    "searchhub": {
      "type": "http",
      "url": "http://<host>:8000/mcp",
      "headers": { "Authorization": "Bearer <token>" }
    }
  }
}
```

或放置 skill 到 `.opencode/skills/searchhub-web/`。

## Gemini CLI

`gemini config` 或 settings 的 `mcp` 段添加 searchhub 服务器，并安装 skill。

## 统一提示

- token 在管理后台「调用方 Token」页创建
- 本机部署可用 stdio：`SEARCHHUB_DATA=... python -m searchhub.mcp`
