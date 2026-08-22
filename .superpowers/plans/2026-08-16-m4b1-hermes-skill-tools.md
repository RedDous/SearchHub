# SearchHub M4B-1：hermes 插件 + agent skill + agent tool 安装包实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付 SearchHub 的消费方接入件（不含 dsh——dsh 独立为 M4B-2）：(1) hermes-agent 原生 provider 插件（`integrations/hermes/`，透传 REST，`supports_extract() -> True`）；(2) agent skill（`integrations/skill/`，SKILL.md，供 opencode/Claude Code/Codex 等安装）；(3) agent tool 安装包（`integrations/tools/`，统一 function-calling tool JSON + 各主流 agent 的 MCP/工具安装片段）。

**Architecture:** hermes 插件严格按 `tmp/hermes-web-backend-spec.md` 第三/四/六节契约：`plugin.yaml`（kind: backend, provides_web_providers: [searchhub]）+ `provider.py`（继承 `agent.web_search_provider.WebSearchProvider`，`is_available()` 仅查 env、`supports_extract() -> True`、同步 httpx 透传 `/v1/search`、`/v1/extract`，响应位对位透传，失败统一 `{"success": False, "error"}`，extract 容忍未知 kwargs）。插件的测试用**本地 hermes ABC 垫片**（sys.modules 注入假的 `agent.web_search_provider`，契约形状与 spec 一致）+ respx mock SearchHub REST——不依赖 hermes 安装。skill 与 tool 包为文档/JSON 件，随仓库分发；MCP 配置片段复用 M3 的 `/mcp` 端点（Bearer token）。

**Tech Stack:** Python（插件 + pytest + respx 测试）；Markdown/JSON（skill、tool 包）；无新运行时依赖。

## Global Constraints

- hermes 插件契约（逐条对照 spec 第三/六节）：`name = "searchhub"`（小写无空格）；`is_available()` 严禁网络调用（读 `SEARCHHUB_URL`/`SEARCHHUB_TOKEN`，经 `get_provider_env` 同时覆盖进程 env 与 `~/.hermes/.env`）；`supports_search()`/`supports_extract()` 均 True；`search(query, limit=5)` 返回 `{"success": True, "data": {"web": [{title,url,description,position}]}}` 位对位透传；`extract(urls, **kwargs)` 返回 `{"success": True, "data": [{url,title,content,raw_content,metadata,error?}]}`，kwargs 容忍未知键（format/include_raw/max_chars 等透传给 REST）；失败统一 `{"success": False, "error": str}`；同步实现（hermes 支持同步/异步均可）
- `plugin.yaml`：`name: web-searchhub`、`version: 1.0.0`、`description`、`author: SearchHub`、`kind: backend`、`provides_web_providers: [searchhub]`
- 插件安装目录目标：`~/.hermes/plugins/web/searchhub/`（README 说明）；仓库源在 `integrations/hermes/`
- skill：`SKILL.md`（frontmatter: name + description），内容含能力说明、配置（SEARCHHUB_URL/TOKEN）、REST 用法与 curl 示例、MCP 用法
- tools：`integrations/tools/` 提供 (a) 统一 function-calling tool JSON（OpenAI 风格 `web_search`/`web_extract`，供自定义 harness）；(b) 各 agent 安装片段：Claude Code（MCP config + skill 安装）、Codex（MCP config + skill）、Cursor（MCP config）、OpenCode（MCP config）、Gemini CLI（MCP config）——原生不支持自定义 tool 的一律回退 MCP 配置片段（M3 端点 `/mcp` + Bearer）
- 测试：hermes 插件用垫片 + respx（4 用例：search 透传、extract 透传、401/错误信封、is_available 不联网）；skill/tools 为文档件——结构测试（SKILL.md 有 frontmatter、tool JSON 可解析且参数 schema 完整）
- pytest 175 基线 + 新增；提交风格 `feat:`/`fix:`/`chore:`

## File Structure

```
integrations/
  README.md                       # 总览：插件/skill/tools 安装总入口
  hermes/
    web-searchhub/
      plugin.yaml
      provider.py
      README.md                   # 安装与配置（hermes plugins list、web.* 配置）
  skill/
    searchhub-web/
      SKILL.md
    README.md
  tools/
    web_search.json               # 统一 function-calling tool 定义（OpenAI 风格）
    web_extract.json
    README.md                     # 各 agent 安装片段（Claude Code/Codex/Cursor/OpenCode/Gemini CLI）
tests/
  test_hermes_plugin.py           # 垫片 + respx
  test_integration_docs.py        # SKILL.md frontmatter + tool JSON 结构
```

---

### Task 1: hermes 插件（plugin.yaml + provider.py + 测试）

**Files:**
- Create: `integrations/hermes/web-searchhub/plugin.yaml`
- Create: `integrations/hermes/web-searchhub/provider.py`
- Create: `integrations/hermes/web-searchhub/README.md`
- Test: `tests/test_hermes_plugin.py`

**Interfaces:**
- Produces `provider.py`（完整内容）:
```python
"""SearchHub aggregator backend for hermes-agent.

Thin passthrough client for a self-hosted SearchHub instance
(REST endpoints /v1/search and /v1/extract).
"""

from agent.web_search_provider import WebSearchProvider, get_provider_env


class SearchHubProvider(WebSearchProvider):
    name = "searchhub"

    def __init__(self) -> None:
        self._base = (get_provider_env("SEARCHHUB_URL") or "").rstrip("/")
        self._token = get_provider_env("SEARCHHUB_TOKEN") or ""

    @property
    def display_name(self) -> str:
        return "SearchHub (self-hosted aggregator)"

    def is_available(self) -> bool:
        return bool(self._base and self._token)

    def supports_search(self) -> bool:
        return True

    def supports_extract(self) -> bool:
        return True

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._token}"}

    def _call(self, method: str, path: str, params: dict | None = None,
              json_body: dict | None = None, timeout: float = 30.0) -> dict:
        import httpx

        url = f"{self._base}{path}"
        try:
            if method == "GET":
                resp = httpx.get(url, params=params, headers=self._headers(), timeout=timeout)
            else:
                resp = httpx.post(url, json=json_body or {}, headers=self._headers(), timeout=timeout)
            body = resp.json()
        except Exception as e:
            return {"success": False, "error": str(e)}
        if resp.status_code != 200 or not isinstance(body, dict):
            return {"success": False, "error": body.get("error") if isinstance(body, dict) else f"http {resp.status_code}"}
        return body

    def search(self, query: str, limit: int = 5) -> dict:
        return self._call("GET", "/v1/search", params={"q": query, "limit": limit})

    def extract(self, urls, **kwargs) -> dict:
        # kwargs 可能携带 format/include_raw/max_chars 等 forward-compat 字段，未知键忽略
        body = {"urls": list(urls)}
        for key in ("format", "include_raw", "max_chars"):
            if key in kwargs and kwargs[key] is not None:
                body[key] = kwargs[key]
        return self._call("POST", "/v1/extract", json_body=body, timeout=90.0)


def register(ctx) -> None:
    ctx.register_web_search_provider(SearchHubProvider())
```

- Produces `plugin.yaml`:
```yaml
name: web-searchhub
version: 1.0.0
description: "SearchHub self-hosted search/extract aggregator backend (thin REST passthrough)."
author: SearchHub
kind: backend
provides_web_providers:
  - searchhub
```

- Produces `README.md`（安装配置，对照 spec 第七节）:
```markdown
# SearchHub hermes 插件

SearchHub 聚合服务的 hermes-agent 原生后端（Route A：顶替内置 web_search / web_extract）。

## 安装

```bash
mkdir -p ~/.hermes/plugins/web/searchhub
cp plugin.yaml provider.py ~/.hermes/plugins/web/searchhub/
# 或在仓库内直接软链：ln -s $(pwd) ~/.hermes/plugins/web/searchhub
hermes plugins list        # 应看到 web-searchhub
```

## 配置

凭据放 `~/.hermes/.env`（插件用 get_provider_env 读取，进程 env 优先）：

```
SEARCHHUB_URL=http://<nas>:8000
SEARCHHUB_TOKEN=<管理后台「调用方 Token」页创建的 token>
```

指向 SearchHub 并启用：

```bash
hermes config set web.backend searchhub
hermes config set web.search_backend searchhub
hermes config set web.extract_backend searchhub
# 修改后 /reset 或重启生效
```

## 验证

- `hermes tools` 的 Web Search/Extract 选择器应出现 SearchHub
- 直接调用 `web_search` 与 `web_extract` 各一次，确认返回契约形状
- 拔掉 SearchHub 服务 → 错误信息应指明连接失败

## 说明

- `is_available()` 不联网（仅查 URL/TOKEN 是否配置）
- 响应由 SearchHub 位对位透传（`data.web[].title/url/description/position`；extract 的 `data[].url/title/content/raw_content/metadata`）
```

- [ ] **Step 1: 写失败测试**

`tests/test_hermes_plugin.py`（本地 hermes ABC 垫片 + respx）:
```python
import importlib
import sys
import types
from typing import Any

import httpx
import pytest
import respx

# ---- hermes 契约垫片（与 agent/web_search_provider 的形状一致）----
def _install_hermes_shim() -> None:
    abc = types.ModuleType("agent.web_search_provider")
    provider_mod = types.ModuleType("agent")
    provider_mod.web_search_provider = abc
    sys.modules.setdefault("agent", provider_mod)
    sys.modules.setdefault("agent.web_search_provider", abc)
    # 在 abc 模块上定义 WebSearchProvider / get_provider_env
    code = """
from abc import ABC, abstractmethod

class WebSearchProvider(ABC):
    name = ""

    @abstractmethod
    def is_available(self) -> bool: ...

    def supports_search(self) -> bool:
        return True

    def supports_extract(self) -> bool:
        return False

    @abstractmethod
    def search(self, query: str, limit: int = 5): ...

    @abstractmethod
    def extract(self, urls, **kwargs): ...

def get_provider_env(key: str) -> str | None:
    import os
    return os.environ.get(key) or _env_file_get(key)

def _env_file_get(key: str) -> str | None:
    import os
    path = os.path.expanduser("~/.hermes/.env")
    try:
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line.startswith(f"{key}="):
                return line[len(key) + 1:]
    except OSError:
        pass
    return None
"""
    exec(code, abc.__dict__)


_install_hermes_shim()

from searchhub_plugin  # noqa: E402
```
> 注：为让 `from agent.web_search_provider import ...` 可用，测试需把 `integrations/hermes/web-searchhub/` 加进 sys.path 并以模块名导入 provider.py——上述 `from searchhub_plugin` 是示意；实现时在测试内：`sys.path.insert(0, str(ROOT / "integrations/hermes/web-searchhub"))` + `import provider`。以实际可行为准，垫片契约形状保持不变。

完整测试（以 `import provider` 方式）:
```python
@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("SEARCHHUB_URL", "http://searchhub:8000")
    monkeypatch.setenv("SEARCHHUB_TOKEN", "tok-123")


def test_is_available_requires_url_and_token(monkeypatch):
    monkeypatch.delenv("SEARCHHUB_URL", raising=False)
    monkeypatch.delenv("SEARCHHUB_TOKEN", raising=False)
    from provider import SearchHubProvider
    p = SearchHubProvider()
    assert p.is_available() is False
    monkeypatch.setenv("SEARCHHUB_URL", "http://x")
    monkeypatch.setenv("SEARCHHUB_TOKEN", "t")
    assert SearchHubProvider().is_available() is True


@pytest.mark.asyncio
async def test_search_passthrough(env):
    from provider import SearchHubProvider
    with respx.mock:
        route = respx.get("http://searchhub:8000/v1/search").mock(
            return_value=httpx.Response(200, json={"success": True, "data": {"web": [
                {"title": "T", "url": "https://a.com", "description": "D", "position": 0}]}}))
        p = SearchHubProvider()
        result = p.search("python", limit=3)
        assert result["success"] is True
        assert result["data"]["web"][0]["title"] == "T"
        sent = route.calls[0].request
        assert sent.url.params["q"] == "python"
        assert sent.headers["authorization"] == "Bearer tok-123"


@pytest.mark.asyncio
async def test_extract_passthrough_with_kwargs(env):
    from provider import SearchHubProvider
    with respx.mock:
        route = respx.post("http://searchhub:8000/v1/extract").mock(
            return_value=httpx.Response(200, json={"success": True, "data": [
                {"url": "https://a.com", "title": "T", "content": "c", "raw_content": "r", "metadata": {}}]}))
        p = SearchHubProvider()
        result = p.extract(["https://a.com"], format="markdown", max_chars=100, include_raw=True, unknown_future="x")
        assert result["success"] is True
        sent = route.calls[0].request
        body = sent.json()
        assert body["urls"] == ["https://a.com"]
        assert body["format"] == "markdown"
        assert "unknown_future" not in body


@pytest.mark.asyncio
async def test_failure_envelope(env):
    from provider import SearchHubProvider
    with respx.mock:
        respx.get("http://searchhub:8000/v1/search").mock(return_value=httpx.Response(500, json={"success": False, "error": "boom"}))
        p = SearchHubProvider()
        result = p.search("python")
        assert result["success"] is False
        assert result["error"] == "boom"


@pytest.mark.asyncio
async def test_transport_error_envelope(env):
    from provider import SearchHubProvider
    with respx.mock:
        respx.get("http://searchhub:8000/v1/search").mock(side_effect=httpx.ConnectError("down"))
        p = SearchHubProvider()
        result = p.search("python")
        assert result["success"] is False
        assert "down" in result["error"]
```
> 说明：hermes 的 search/extract 为同步方法，测试用同步调用即可（去掉 @pytest.mark.asyncio 亦可——按实际实现保留同步测试）。

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/pytest tests/test_hermes_plugin.py -v`
Expected: FAIL（provider 模块/文件不存在）

- [ ] **Step 3: 实现**

按 Interfaces 创建三个文件。注意 provider.py 顶部 docstring 与 `import httpx` 放方法内（懒加载，避免插件安装环境缺 httpx 时导入即崩——hermes 依赖里有 httpx，但防御性懒加载无害）。

- [ ] **Step 4: 运行确认通过 + 全量回归**

Run: `.venv/bin/pytest tests/test_hermes_plugin.py -v && .venv/bin/pytest -q`
Expected: 新增通过；全量 175 + 4 = 179 全绿

- [ ] **Step 5: 提交**

```bash
git add integrations/hermes tests/test_hermes_plugin.py
git commit -m "feat: hermes-agent searchhub provider plugin with tests"
```
---

### Task 2: agent skill（SKILL.md）

**Files:**
- Create: `integrations/skill/searchhub-web/SKILL.md`
- Create: `integrations/skill/README.md`
- Test: `tests/test_integration_docs.py`（本任务先写 SKILL.md 结构断言部分）

**Interfaces:**
- Produces `SKILL.md`（frontmatter 格式，兼容 opencode/Claude Code/Codex 的 agent skills）:
```markdown
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
```

- Produces `integrations/skill/README.md`：安装方式（opencode: `~/.config/opencode/skills/` 或项目 `.opencode/skills/`；Claude Code: `~/.claude/skills/`；Codex: `~/.codex/skills/`）——复制 `searchhub-web/` 目录即可

- [ ] **Step 1: 写结构测试（本任务先建文件）**

`tests/test_integration_docs.py`（Task 3 会扩展）:
```python
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_skill_has_frontmatter():
    skill = (ROOT / "integrations/skill/searchhub-web/SKILL.md").read_text()
    assert skill.startswith("---\n")
    assert "name: searchhub-web" in skill.split("---")[1]
    assert "description:" in skill.split("---")[1]


def test_skill_mentions_both_endpoints():
    skill = (ROOT / "integrations/skill/searchhub-web/SKILL.md").read_text()
    assert "/v1/search" in skill
    assert "/v1/extract" in skill
    assert "SEARCHHUB_URL" in skill and "SEARCHHUB_TOKEN" in skill
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/pytest tests/test_integration_docs.py -v`
Expected: FAIL（文件不存在）

- [ ] **Step 3: 创建文件**

按 Interfaces 创建 SKILL.md 与 skill/README.md。

- [ ] **Step 4: 运行确认通过 + 提交**

Run: `.venv/bin/pytest tests/test_integration_docs.py -v && .venv/bin/pytest -q`
Expected: 通过；全量 181 全绿

```bash
git add integrations/skill tests/test_integration_docs.py
git commit -m "feat: agent skill (SKILL.md) for SearchHub search/extract"
```

---

### Task 3: agent tool 安装包（统一 tool JSON + 各 agent 片段）

**Files:**
- Create: `integrations/tools/web_search.json`
- Create: `integrations/tools/web_extract.json`
- Create: `integrations/tools/README.md`
- Create: `integrations/README.md`（总览）
- Modify: `tests/test_integration_docs.py`（tool JSON 结构断言）

**Interfaces:**
- Produces `web_search.json`（OpenAI function-calling 风格，供任意支持自定义 tool 的 harness 直接使用）:
```json
{
  "type": "function",
  "function": {
    "name": "web_search",
    "description": "Search the web through the SearchHub aggregator. Returns JSON with {success, data: {web: [{title, url, description, position}]}, meta}.",
    "parameters": {
      "type": "object",
      "properties": {
        "query": {"type": "string", "description": "Search query"},
        "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 5},
        "providers": {"type": "string", "description": "Comma-separated provider ids to restrict to (exa,tavily,ddg,searxng,jina,trafilatura)"},
        "strategy": {"type": "string", "enum": ["fanout", "rotation", "primary_fallback"]}
      },
      "required": ["query"]
    }
  }
}
```
- Produces `web_extract.json`（同上风格）: `name: web_extract`、`urls: array of string`（必填）、`format: enum [markdown, text]`、`max_chars: integer 100-1000000 default 15000`
- Produces `integrations/tools/README.md`（各 agent 安装片段）:
  - **通用（自定义 harness）**：直接用两个 JSON 文件注册工具；调用 = `POST {SEARCHHUB_URL}/v1/search`（Bearer token），响应透传给模型
  - **Claude Code**：`claude mcp add searchhub --transport http http://<host>:8000/mcp --header "Authorization: Bearer <token>"`（或 `~/.claude.json` 的 mcpServers 配置）；skill 安装见 integrations/skill
  - **Codex**：`~/.codex/config.toml` 的 mcp_servers（stdio 或 http）+ `~/.codex/skills/searchhub-web/` 复制 skill
  - **Cursor**：Settings → MCP → Add → URL `http://<host>:8000/mcp` + Header `Authorization: Bearer <token>`
  - **OpenCode**：`opencode.json` 的 mcp 段（type http, url + headers）或 `.opencode/skills/searchhub-web/`
  - **Gemini CLI**：`gemini config` 或 settings 的 mcp 段 + skill
  - 统一提示：token 在管理后台「调用方 Token」页创建；本机部署可用 stdio：`SEARCHHUB_DATA=... python -m searchhub.mcp`
- Produces `integrations/README.md`（总览）: 四类接入（hermes 插件 / skill / tools / MCP）的适用场景与安装入口
- 测试追加:
```python
import json


def test_tool_json_definitions_valid():
    for name in ("web_search", "web_extract"):
        path = ROOT / "integrations/tools" / f"{name}.json"
        doc = json.loads(path.read_text())
        assert doc["type"] == "function"
        fn = doc["function"]
        assert fn["name"] == name
        props = fn["parameters"]["properties"]
        assert "type" in props or "urls" in props
        assert fn["parameters"]["required"]


def test_tools_readme_covers_agents():
    readme = (ROOT / "integrations/tools/README.md").read_text()
    for agent in ("Claude Code", "Codex", "Cursor", "OpenCode", "Gemini CLI"):
        assert agent in readme
    assert "/mcp" in readme


def test_integrations_overview_readme():
    readme = (ROOT / "integrations/README.md").read_text()
    for section in ("hermes", "skill", "tools", "MCP"):
        assert section in readme
```

- [ ] **Step 1: 写失败测试**

在 `tests/test_integration_docs.py` 追加上述 3 个测试，运行确认失败（文件不存在）。

- [ ] **Step 2: 创建文件**

按 Interfaces 创建 4 个文件（tool JSON、tools/README、integrations/README）。

- [ ] **Step 3: 验证 + 全量回归**

Run: `.venv/bin/pytest tests/test_integration_docs.py -v && .venv/bin/pytest -q`
Expected: 通过；全量 184 全绿

- [ ] **Step 4: 提交**

```bash
git add integrations tests/test_integration_docs.py
git commit -m "feat: agent tool packages and integrations overview"
```

---

## Self-Review

- **Spec 覆盖**（设计文档 §四 二期接入形态）：hermes 插件 → Task 1（Route A 原生 provider，supports_extract True，薄透传，is_available 不联网）；agent skill → Task 2；agent tool 安装包 → Task 3（统一 function-calling JSON + 各 agent MCP/工具安装片段，原生不支持自定义 tool 的回退 MCP——M3 端点）。dsh 插件不在本计划（M4B-2）。
- **占位符扫描**：Task 1 插件完整代码与 4 个测试；Task 2/3 文档内容完整、测试明确。
- **类型一致性**：插件 `name="searchhub"` 与 plugin.yaml `provides_web_providers: [searchhub]` 一致；REST 契约（/v1/search、/v1/extract、Bearer）与 M1/M3 实现一致；tool JSON 的 tool 名与 M3 MCP 工具名一致（web_search/web_extract）。
- 已知取舍：hermes 插件测试用本地垫片（不依赖 hermes 安装，契约形状按 spec 第三节）；skill/tools 为文档件（结构测试兜底，行为验证在真实 agent 环境由用户执行）；dsh 插件接口需按当时版本核对（M4B-2）。
