# SearchHub MCP 接入

MCP（Model Context Protocol）接入，让 AI 客户端（opencode / claude / cursor 等）直接调用 SearchHub 的搜索与提取能力。提供两个工具，返回单一 JSON 字符串（成功时形状与 REST `/v1` 的 data 部分一致，不含 `success` 标志——客户端按形状或错误字段探测）：

- `web_search(query, limit?, providers?, strategy?)`：网页搜索
- `web_extract(urls, format?, max_chars?)`：网页内容提取

支持两种传输：

## streamable-http（经主服务挂载于 `/mcp`，推荐远端使用）

随主服务一起启动，无需额外进程。需要调用方 Token（管理后台「调用方 Token」页创建）：

```json
{
  "mcpServers": {
    "searchhub": {
      "url": "http://<host>:8000/mcp",
      "headers": {
        "Authorization": "Bearer <token>"
      }
    }
  }
}
```

## stdio（本地 CLI，本机直接运行）

无需 Token，直接运行主服务所在环境的 MCP 服务：

```bash
SEARCHHUB_DATA=/path/to/searchhub/data python -m searchhub.mcp
```

MCP 客户端配置示例：

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

> Docker 部署时 stdio 模式在宿主机执行：`python -m searchhub.mcp` 需要宿主机有 Python 与 searchhub 包；否则请使用 streamable-http 方式指向 `http://<NAS-IP>:8000/mcp`。

## 鉴权

streamable-http 通过 `Authorization: Bearer <token>` 请求头携带 Token（与 REST `/v1` 同一套调用方 Token）；token 缺失或无效返回 401。stdio 模式本地直连，无需 Token。

## 验证

```bash
# stdio 冒烟：正常时会持续等待标准输入，3 秒后被 timeout 终止（exit=124）
timeout 3 SEARCHHUB_DATA=/path/to/searchhub/data python -m searchhub.mcp; echo "exit=$?"
```

随后在任意 MCP 客户端（opencode / claude / cursor）中按上面的配置连接，调用 `web_search` / `web_extract` 即可。所有调用会记录在主服务的管理后台「历史查询」页。