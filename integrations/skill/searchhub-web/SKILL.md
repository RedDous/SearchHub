---
name: searchhub-web
description: 通过 SearchHub 聚合服务执行网页搜索与内容提取。Use when the agent needs current web information, search results, or page content extraction — including multi-provider aggregated results. 用法：配置 SEARCHHUB_URL 与 SEARCHHUB_TOKEN 后调用 REST 或 MCP。
---

# SearchHub Web Search & Extract

通过自托管 SearchHub 聚合服务（多供应商：exa/tavily/ddg/searxng/jina/trafilatura 等）执行搜索与网页提取。

## 配置

- 环境变量或工具配置中提供：`SEARCHHUB_URL`（如 `http://192.168.1.10:8000`）、`SEARCHHUB_TOKEN`（管理后台「调用方 Token」页创建）
- 无 token 时 REST 返回 401：`{"success": false, "error": "invalid token"}`

## REST 用法

### 搜索

```bash
curl -s "$SEARCHHUB_URL/v1/search" \
  -H "Authorization: Bearer $SEARCHHUB_TOKEN" \
  -G --data-urlencode "q=your query" --data-urlencode "limit=5"
```

响应（成功）：
```json
{"success": true, "data": {"web": [
  {"title": "...", "url": "...", "description": "...", "position": 0}
]}, "meta": {"took_ms": 320, "cached": false}}
```

### 提取

```bash
curl -s "$SEARCHHUB_URL/v1/extract" \
  -H "Authorization: Bearer $SEARCHHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"urls": ["https://example.com"], "format": "markdown", "max_chars": 15000}'
```

响应（成功）：`data` 为数组，每项 `{url, title, content, raw_content, metadata}`；单 URL 失败时该项带 `error` 字段。

### 其他端点

- `GET /v1/providers`：当前可用供应商与能力
- `GET /healthz` / `GET /readyz`：健康检查

## MCP 用法（可选）

若 agent 支持 MCP：`http://<SEARCHHUB_URL>/mcp`，`Authorization: Bearer <token>` 请求头；工具 `web_search(query, limit?, providers?, strategy?)`、`web_extract(urls, format?, max_chars?)`。

## 失败处理

- 响应 `{"success": false, "error": "..."}`：展示 error 给用户，可重试一次
- 401：token 无效或已吊销，提示用户去管理后台重新创建
- 网络失败：SearchHub 未启动或地址错误