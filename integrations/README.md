# SearchHub 接入总览

SearchHub 提供四类接入方式，按 agent/harness 能力与场景选用：

| 接入方式 | 适用场景 | 安装入口 |
| --- | --- | --- |
| **hermes 插件** | hermes-agent：原生 provider，薄透传，`is_available` 不联网 | [integrations/hermes](hermes/) |
| **skill** | 支持 skill/instruction 注入的 agent（Claude Code、Codex、OpenCode 等） | [integrations/skill](skill/searchhub-web/SKILL.md) |
| **tools** | 任意支持自定义 tool 的 harness：统一 function-calling JSON + 各 agent 安装片段 | [integrations/tools](tools/README.md) |
| **MCP** | 支持 MCP 的 agent（Claude Code、Cursor、Codex、OpenCode、Gemini CLI 等）；原生不支持自定义 tool 时的回退 | `http://<host>:8000/mcp`（Bearer token） |
| **dsh 插件** | dsh（dev-preview）：`ctx.web` seam 的 SearchHub 供应商，search + fetch 双能力，含设置段与凭据引用 | [integrations/dsh/searchhub-web](dsh/searchhub-web/README.md) |

## 共同前提

- 部署 SearchHub 服务，设置 `SEARCHHUB_URL` 与 `SEARCHHUB_TOKEN`
- token 在管理后台「调用方 Token」页创建
- 所有方式共用同一套工具语义：`web_search`（搜索）与 `web_extract`（提取），REST 契约 `/v1/search`、`/v1/extract`

## 选型建议

- hermes-agent → 插件（性能最好，无额外依赖）
- 支持 MCP 的 agent → MCP（统一入口，无需按 agent 维护）
- 支持 skill 的 agent → skill（prompt 级集成，含失败处理指引）
- 自定义 harness / 原生不支持自定义 tool → tools 目录的 JSON + 安装片段
- dsh（dev-preview）→ dsh 插件（`ctx.web` seam 原生接线，设置段 + 凭据引用）
