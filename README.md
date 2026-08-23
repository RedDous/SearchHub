# SearchHub

自托管统一 Web 搜索 / 网页提取聚合服务。一个服务聚合多家搜索与提取供应商（exa / tavily / ddg / searxng / jina / trafilatura ...），统一管理 API Key 与多 Key 轮换，为你的 AI Agent 提供稳定可靠的搜索与网页提取能力。

- 多供应商聚合：并发 / 轮换 / 主备调度，失败自动剔除、按质量权重合并排序
- 多 Key 管理：每个云供应商支持多个 Key 自动轮换、限速与故障冷却
- 全量 UI 管理：供应商、Key、策略、缓存、Token、历史与统计均在管理后台完成，无需编辑配置文件
- Agent 接入：REST API、MCP、hermes 插件、dsh 插件、Agent Skill、工具安装包
- 一键部署：Docker Compose，NAS 友好，零环境依赖

## 快速部署（Docker）

适合 NAS 等自托管场景。前提：已安装 Docker 与 Docker Compose v2。两种方式任选：

**方式 A：拉取镜像（推荐）**

无需拉取源码，直接拉取镜像运行：

```bash
mkdir -p data
docker run -d --name searchhub \
  -p 8000:8000 \
  -v "$PWD/data:/data" \
  -e SEARCHHUB_DATA=/data \
  -e ADMIN_PASSWORD=admin \
  --restart unless-stopped \
  ghcr.io/reddous/searchhub:latest
```

**方式 B：源码构建**

```bash
git clone https://github.com/RedDous/SearchHub.git && cd SearchHub
docker compose -f docker-compose.yml -f docker-compose.build.yml up -d --build
```

打开 `http://<NAS-IP>:8000`：

1. 首次登录默认账号 `admin / admin`（若在 `.env` 设置了 `ADMIN_PASSWORD` 则为该值），登录后系统会强制要求修改密码
2. 登录后按管理后台引导完成配置：供应商、Key、调用方 Token 等

**数据与备份**：
- 全部数据位于 `./data/`（config.yaml、secrets.env、history.db、cache.db、session_secret）。
- 备份 = 拷贝整个目录；恢复 = 拷贝回去后重启服务。

**说明**：

- `.env` 完全可选——不创建也能零配置启动（首次密码即默认 admin）；如密码含 `$` 请用 `$$` 转义（可复制 `.env.example` 作为模板）
- 前端已内置镜像，无需单独构建（方式 A 直接拉取；方式 B 的 `--build` 已包含前端编译）
- 镜像内以 root 运行（家用场景简化；如需非 root 可在 compose 加 `user:`）

## 供应商配置

在管理后台「供应商」页按目录点选类型，即可进入该供应商的专属配置表单：

| 供应商 | 能力 | 配置要点 |
|---|---|---|
| exa | search + extract | 云端 API，需 API Key（可配置多个自动轮换） |
| tavily | search + extract | 云端 API，需 API Key |
| ddg（DuckDuckGo） | search | 免 Key，启用即可 |
| searxng | search | 自建实例，需填写 base_url |
| jina | extract | 免 Key（可选 Key 提升免费配额） |
| trafilatura | extract | 免 Key，内置本地提取 |

各供应商的配置表单由类型 schema 驱动（字段按需显示），保存后可在页面执行「连接测试」验证；所有 Key 以掩码显示、绝不回显。

## 功能接入

| 方式 | 说明 | 入口 |
|---|---|---|
| REST API | `/v1/search` / `/v1/extract` 等，Bearer Token 鉴权 | 管理后台「调用方 Token」页创建 |
| MCP | streamable-http（`/mcp`）与 stdio 两种传输，工具 `web_search` / `web_extract` | 按各 MCP 客户端配置 |
| hermes 插件 | hermes-agent 原生后端，顶替内置 web_search / web_extract | `integrations/hermes/` |
| dsh 插件 | DeepSeek Harness web seam（search + fetch） | `integrations/dsh/` |
| Agent Skill | opencode / Claude Code / Codex 等技能目录 | `integrations/skill/` |
| 工具安装包 | 自定义 harness 的 function-calling 定义及主流 agent 安装片段 | `integrations/tools/` |