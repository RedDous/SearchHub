# SearchHub M3：MCP Server 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 SearchHub 提供 MCP（Model Context Protocol）接入：`web_search` / `web_extract` 两个工具，支持 streamable-http（挂载 FastAPI `/mcp`）与 stdio（`python -m searchhub.mcp`）两种传输，复用现有引擎、缓存、配置与调用方 Token 鉴权。

**Architecture:** 使用官方 `mcp` Python SDK 2.x 的 `MCPServer`。工具函数通过模块级引擎钩子 `_get_engine()` 懒取 SearchHubEngine（FastAPI lifespan 或 stdio main 各自 `set_engine`）。HTTP 路径：`mcp.streamable_http_app()` 外包一层 ASGI 鉴权中间件（校验 `Authorization: Bearer <token>` 与现有调用方 Token 一致），挂载到 FastAPI `/mcp`；宿主 lifespan 必须执行 `async with mcp.session_manager.run()`（挂载子应用 lifespan 不执行）。stdio 路径：`searchhub/mcp.py` 入口构建独立引擎并 `mcp.run()`。工具返回单一 JSON 字符串（成功 = 数据形状与 REST data 一致；失败 = `{"success": false, "error": ...}`）。

**Tech Stack:** mcp>=2.0.0（官方 Python SDK）、FastAPI（既有）、pytest + pytest-asyncio；客户端侧测试用 SDK 自带 `ClientSession`（stdio 子进程全协议往返）。

## Global Constraints

- 依赖：pyproject 追加 `mcp>=2.0.0`；Python >= 3.11；提交风格 `feat:`/`fix:`/`chore:`
- 工具返回**单一 JSON 字符串**：成功 → `json.dumps(resp.data.model_dump())`（search 为 `{"web": [...]}`，extract 为 items 数组）；失败 → `json.dumps({"success": False, "error": resp.error})`（MCP 工具不抛异常）
- HTTP 鉴权强制：无 `Authorization: Bearer <token>` 或 token 无效 → 401 且 body 为统一错误形状 `{"success": false, "error": "invalid token"}`；与 `api/auth.py` 的 `_authorized` 逻辑一致（sha256 + 常量时间比较 + 跳过 revoked）
- 挂载：`app.mount("/mcp", <wrapped asgi>)`；FastAPI lifespan 内 `async with mcp.session_manager.run(): yield`；引擎钩子在 lifespan 内 `set_engine(engine)`（必须早于任何 MCP 请求）
- 引擎钩子线程安全：模块级单例，`set_engine` 只设置一次（第二次调用覆盖并记 debug 日志）
- 现有 142 个 pytest 与 17 个 vitest 必须保持全绿；MCP 改动不得影响 `/api/*`、`/v1/*`、静态托管
- 文档：README 追加 MCP 章节（stdio 与 streamable-http 配置示例）

## File Structure

```
pyproject.toml                    # + mcp>=2.0.0
src/searchhub/
  mcp_server.py                   # 引擎钩子、create_mcp_server()、web_search/web_extract 工具、
                                  #   ASGI 鉴权包装、build_mcp_asgi()、stdio main()
  mcp.py                          # `python -m searchhub.mcp` 入口（转调 mcp_server.main）
  api/app.py                      # 挂载 /mcp + lifespan session_manager + set_engine
tests/
  test_mcp_tools.py               # 工具函数单测（FakeProvider 引擎）
  test_mcp_auth.py                # ASGI 鉴权（无/坏/好 token）
  test_mcp_stdio_e2e.py           # ClientSession stdio 全协议往返
README.md                         # MCP 章节
```

---

### Task 1: MCP 服务器核心（MCPServer + 工具 + 引擎钩子 + stdio 入口）

**Files:**
- Modify: `pyproject.toml`（dependencies 追加 `"mcp>=2.0.0"`）
- Create: `src/searchhub/mcp_server.py`
- Create: `src/searchhub/mcp.py`
- Test: `tests/test_mcp_tools.py`

**Interfaces:**
- Produces（mcp_server.py）:
  - `def set_engine(engine: SearchHubEngine) -> None` / `def _get_engine() -> SearchHubEngine`（未设置时抛 `RuntimeError("MCP engine not set")`）
  - `def create_mcp_server() -> MCPServer`——服务名 `"SearchHub"`，注册两个工具（docstring 即工具描述）：
    - `async def web_search(query: str, limit: int = 5, providers: str | None = None, strategy: str | None = None) -> str`——调 `_get_engine().search(query, limit=limit, providers=providers, strategy=strategy)`；返回 JSON 字符串（见 Global Constraints）
    - `async def web_extract(urls: list[str], format: str = "markdown", max_chars: int = 15000) -> str`——调 `_get_engine().extract(urls, fmt=format, max_chars=max_chars)`；返回 JSON 字符串
    - 注意：`web_extract` 的参数名 `format` 在 MCP 输入 schema 中照原样暴露；`limit` 参数 `ge=1, le=50`、`max_chars` `ge=100, le=1000000` 用工具函数注解直接声明（SDK 从类型注解生成 schema；范围约束用 `Annotated[int, Field(ge=1, le=50)]`，pydantic Field 支持）
  - `def build_mcp_asgi() -> ASGIApp`——`create_mcp_server().streamable_http_app()` 包一层鉴权（Task 3 才实现鉴权包装；本任务先返回裸 app，鉴权在 Task 3 的包装器接入——为避免返工，本任务直接实现 `_auth_wrapper` 并在 build_mcp_asgi 中包上，鉴权测试在 Task 3）
  - `def main() -> None`——stdio 入口：`SEARCHHUB_DATA` env（默认 `./data`）构建 ConfigService/CacheRepo/RequestLogRepo/httpx client/SearchHubEngine，`set_engine(engine)`，`mcp.run()`（stdio）；退出后 `await` 关闭 http/cache/history（用 `asyncio.run` 包一层）
- Produces（mcp.py）:
  ```python
  from searchhub.mcp_server import main
  if __name__ == "__main__":
      main()
  ```
- `pyproject.toml` dependencies 追加 `"mcp>=2.0.0"`（`pip install -e ".[dev]"` 后生效）

- [ ] **Step 1: 安装依赖并确认 SDK API**

Run: `.venv/bin/pip install -e ".[dev]" && .venv/bin/python -c "from mcp.server.mcpserver import MCPServer; print('mcp ok')"`
Expected: `mcp ok`（SDK 2.x；若 API 有出入，以安装版本实际 API 为准并记录偏差）

- [ ] **Step 2: 写失败测试**

`tests/test_mcp_tools.py`（复用 FakeProvider 模式；直接调工具函数）:
```python
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from searchhub.config import ConfigService, ProviderConfig
from searchhub.mcp_server import _get_engine, set_engine
from searchhub.models import SearchItem
from searchhub.orchestrator import SearchHubEngine


class FakeProvider:
    id = "fake"
    capabilities = frozenset({"search", "extract"})

    def __init__(self, pid, fail=False):
        self.id = pid
        self.cfg = SimpleNamespace(id=pid, capabilities=["search", "extract"],
                                   weight=10, priority=100, max_results=8)
        self.fail = fail

    def supports(self, cap):
        return cap in self.capabilities

    async def search(self, query, limit):
        if self.fail:
            from searchhub.providers.base import ProviderError
            raise ProviderError(self.id, "boom")
        return [SearchItem(title=query, url=f"https://{self.id}.com", position=0, provider=self.id)]

    async def extract(self, urls, **kw):
        from searchhub.models import ExtractItem
        return [ExtractItem(url=u, content="c", provider=self.id) for u in urls]


def make_engine(data_dir: Path, fail=False):
    cs = ConfigService(data_dir)
    cs.load()
    cfg = cs.get()
    cfg.providers = [ProviderConfig(id="fake", capabilities=["search", "extract"])]
    cs.save_config(cfg)
    engine = SearchHubEngine(cs, None, httpx.AsyncClient())
    engine._registry = {"fake": FakeProvider("fake", fail=fail)}
    engine._version = cs.config_version
    return engine


@pytest.fixture
def engine(data_dir: Path):
    e = make_engine(data_dir)
    set_engine(e)
    yield e
    set_engine(None)  # 钩子复位——set_engine 需支持传 None 清除


async def test_web_search_tool_returns_json_string(engine):
    from searchhub.mcp_server import create_mcp_server

    mcp = create_mcp_server()
    tools = {t.name: t for t in await mcp.list_tools()}
    assert "web_search" in tools and "web_extract" in tools
    result = await tools["web_search"].func("python", 3)
    assert isinstance(result, str)
    data = json.loads(result)
    assert data["web"][0]["title"] == "python"
    assert data["web"][0]["url"] == "https://fake.com"


async def test_web_search_tool_failure_json(engine):
    from searchhub.mcp_server import create_mcp_server

    engine._registry["fake"].fail = True
    mcp = create_mcp_server()
    tools = {t.name: t for t in await mcp.list_tools()}
    result = json.loads(await tools["web_search"].func("python", 3))
    assert result["success"] is False
    assert "boom" in result["error"]


async def test_web_extract_tool_returns_json_string(engine):
    from searchhub.mcp_server import create_mcp_server

    mcp = create_mcp_server()
    tools = {t.name: t for t in await mcp.list_tools()}
    result = json.loads(await tools["web_extract"].func(["https://a.com"], "markdown", 15000))
    assert result[0]["url"] == "https://a.com"
    assert result[0]["content"] == "c"


async def test_get_engine_raises_when_unset():
    from searchhub.mcp_server import _get_engine

    set_engine(None)
    with pytest.raises(RuntimeError):
        _get_engine()
```
> 注：`mcp.list_tools()` 返回 Tool 对象列表，`Tool.func` 为可调用（SDK 2.x 结构，以实际 API 为准；若不同则用 `call_tool` 或等价方式调用工具并断言输出）。`set_engine(None)` 清除钩子。

- [ ] **Step 3: 运行确认失败**

Run: `.venv/bin/pytest tests/test_mcp_tools.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 4: 实现 mcp_server.py**

`src/searchhub/mcp_server.py`:
```python
from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Annotated

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from searchhub.config import ConfigService
from searchhub.orchestrator import SearchHubEngine
from searchhub.storage.cache import CacheRepo
from searchhub.storage.history import RequestLogRepo

logger = logging.getLogger(__name__)

_engine: SearchHubEngine | None = None


def set_engine(engine: SearchHubEngine | None) -> None:
    global _engine
    _engine = engine


def _get_engine() -> SearchHubEngine:
    if _engine is None:
        raise RuntimeError("MCP engine not set")
    return _engine


def create_mcp_server() -> MCPServer:
    mcp = MCPServer("SearchHub")

    @mcp.tool()
    async def web_search(
        query: str,
        limit: Annotated[int, Field(ge=1, le=50)] = 5,
        providers: str | None = None,
        strategy: str | None = None,
    ) -> str:
        """Search the web and return results as a JSON string."""
        resp = await _get_engine().search(
            query, limit=limit, providers=providers, strategy=strategy)
        if not resp.success:
            return json.dumps({"success": False, "error": resp.error}, ensure_ascii=False)
        return json.dumps(resp.data.model_dump(), ensure_ascii=False)

    @mcp.tool()
    async def web_extract(
        urls: list[str],
        format: str = "markdown",
        max_chars: Annotated[int, Field(ge=100, le=1_000_000)] = 15000,
    ) -> str:
        """Extract content from web pages and return a JSON string."""
        resp = await _get_engine().extract(urls, fmt=format, max_chars=max_chars)
        if not resp.success:
            return json.dumps({"success": False, "error": resp.error}, ensure_ascii=False)
        return json.dumps([i.model_dump() for i in resp.data], ensure_ascii=False)

    return mcp


async def _run_stdio() -> None:
    data_dir = Path(os.environ.get("SEARCHHUB_DATA", "data"))
    config = ConfigService(data_dir)
    config.load()
    cache = CacheRepo(data_dir / "cache.db")
    http = httpx.AsyncClient(timeout=60)
    history = RequestLogRepo(data_dir / "history.db")
    engine = SearchHubEngine(config, cache, http, history=history)
    engine.maybe_reload()
    set_engine(engine)
    try:
        await create_mcp_server().run_stdio_async()
    finally:
        await http.aclose()
        await cache.close()
        await history.close()


def main() -> None:
    asyncio.run(_run_stdio())


def build_mcp_asgi():
    return create_mcp_server().streamable_http_app()
```
（import 补 `import httpx`；`build_mcp_asgi` 的鉴权包装在 Task 3 改造。）

`src/searchhub/mcp.py`:
```python
from searchhub.mcp_server import main

if __name__ == "__main__":
    main()
```

- [ ] **Step 5: 运行确认通过**

Run: `.venv/bin/pytest tests/test_mcp_tools.py -v`
Expected: PASS（4 passed）（若 `Tool.func` API 不同，按实际调整测试调用方式并记录偏差）

- [ ] **Step 6: 全量回归 + 提交**

Run: `.venv/bin/pytest -v`
Expected: 142 + 4 = 146 全绿

```bash
git add pyproject.toml src/searchhub/mcp_server.py src/searchhub/mcp.py tests/test_mcp_tools.py
git commit -m "feat: MCP server core with web_search/web_extract tools and stdio entry"
```

---

### Task 2: stdio 全协议端到端测试（ClientSession）

**Files:**
- Test: `tests/test_mcp_stdio_e2e.py`

**Interfaces:**
- Consumes: `python -m searchhub.mcp`（stdio），`SEARCHHUB_DATA` env
- Produces: 无新代码，仅测试——验证真实 MCP 协议往返（initialize → list_tools → call_tool）

- [ ] **Step 1: 写失败测试**

`tests/test_mcp_stdio_e2e.py`:
```python
import json
import os
import sys
from pathlib import Path

import pytest

from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client


@pytest.fixture
async def session(data_dir: Path):
    env = dict(os.environ)
    env["SEARCHHUB_DATA"] = str(data_dir)
    async with stdio_client([sys.executable, "-m", "searchhub.mcp"], env=env) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            yield s


async def test_initialize_and_list_tools(session):
    tools = await session.list_tools()
    names = [t.name for t in tools.tools]
    assert "web_search" in names
    assert "web_extract" in names


async def test_call_web_search_returns_json_string(session):
    result = await session.call_tool("web_search", {"query": "python"})
    # 无供应商配置 → success=false 的 JSON 字符串
    text = result.content[0].text
    data = json.loads(text)
    assert data["success"] is False
    assert "no search provider" in data["error"]


async def test_call_web_extract_returns_json_string(session):
    result = await session.call_tool("web_extract", {"urls": ["https://example.com"]})
    text = result.content[0].text
    data = json.loads(text)
    assert data["success"] is False  # 无 extract 供应商
```
> 说明：stdio 子进程在干净 data 目录运行（无供应商），验证协议层与 JSON 字符串形状；真实供应商行为已由 Task 1 单测覆盖。若 SDK 2.x 的 `call_tool` 返回结构不同（如 `result.content[0].text`），按实际调整。

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/pytest tests/test_mcp_stdio_e2e.py -v`
Expected: FAIL（无法连接或工具缺失——子进程启动问题先于协议断言暴露）

- [ ] **Step 3: 修复实现直至通过**

若子进程无法启动（模块解析、依赖、config 生成问题），修 mcp_server.py/mcp.py；若 SDK 客户端 API 变化，调整测试调用方式。
Run: `.venv/bin/pytest tests/test_mcp_stdio_e2e.py -v`
Expected: PASS（3 passed）

- [ ] **Step 4: 全量回归 + 提交**

Run: `.venv/bin/pytest -v`
Expected: 全绿（149）

```bash
git add tests/test_mcp_stdio_e2e.py
git commit -m "test: stdio MCP end-to-end protocol round-trip"
```

---

### Task 3: HTTP 挂载 + 鉴权 + lifespan 集成

**Files:**
- Modify: `src/searchhub/mcp_server.py`（`build_mcp_asgi` 加鉴权包装）
- Modify: `src/searchhub/api/app.py`（mount /mcp + lifespan session_manager + set_engine）
- Test: `tests/test_mcp_auth.py`

**Interfaces:**
- Produces（mcp_server.py）:
  - `async def _auth_wrapper(scope, receive, send)`：`scope["type"] == "http"` 时校验 `Authorization: Bearer <token>`（从 `scope["headers"]` 取 bytes 的 `b"authorization"` 头）；token 缺失/无效 → 直接 `JSONResponse({"success": False, "error": "invalid token"}, status_code=401)` 发响应并 return；通过 → 调内层 app。非 http scope（lifespan/websocket）直接透传
  - token 校验复用 `searchhub.api.auth._authorized(config, token)`（`from searchhub.api.auth import _authorized`；该函数已跳过 revoked）
  - `build_mcp_asgi()` 改为返回包装后的 ASGI app：`mcp_app = create_mcp_server().streamable_http_app()`，`return _auth_wrapper(mcp_app)`——实现为闭包形式：`async def app(scope, receive, send): ...`
- Produces（app.py）:
  - import：`from searchhub.mcp_server import build_mcp_asgi, set_engine as mcp_set_engine`
  - lifespan：`async with mcp.session_manager.run():` ——需要持有 MCPServer 实例。调整：`mcp_server = create_mcp_server()` 在 lifespan 内创建，`async with mcp_server.session_manager.run():` 包住 `yield` 及引擎初始化；`mcp_set_engine(engine)` 在引擎创建后调用；`app.state.mcp = mcp_server`（测试可读）
  - `create_app` 末尾（所有路由/静态之后、return 前）：`app.mount("/mcp", build_mcp_asgi())`——注意 build_mcp_asgi 每次调用创建新 MCPServer 实例，而 lifespan 里的 session_manager 属于另一个实例——**必须共享同一实例**：把 `create_mcp_server()` 提到 `create_app` 内创建一次，lifespan 与 mount 都用它。实现：
    ```python
    mcp_server = create_mcp_server()
    @asynccontextmanager
    async def lifespan(app):
        ...
        mcp_set_engine(engine)
        async with mcp_server.session_manager.run():
            yield
        ...
    ...
    app.mount("/mcp", _auth_wrap(mcp_server.streamable_http_app()))
    ```
    （`_auth_wrap` 接受内层 app 返回包装 ASGI）
- 挂载顺序：`/mcp` mount 放在静态托管 catch-all **之前**（catch-all 会吞掉未匹配路径——mount 先注册则先匹配，但 catch-all 是 `/{full_path:path}` 会拦截一切；FastAPI 按注册顺序匹配，mount 在 catch-all 之前即可正确命中）

- [ ] **Step 1: 写失败测试**

`tests/test_mcp_auth.py`:
```python
from fastapi.testclient import TestClient

from searchhub.api.app import create_app
from searchhub.config import ConfigService, TokenEntry
import hashlib


def make_client(data_dir, tokens=()):
    cs = ConfigService(data_dir)
    cs.load()
    cfg = cs.get()
    cfg.auth.tokens = list(tokens)
    cs.save_config(cfg)
    return TestClient(create_app(data_dir))


def test_mcp_requires_token(data_dir):
    with make_client(data_dir) as c:
        r = c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                 "params": {"protocolVersion": "2025-03-26",
                                            "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}})
        assert r.status_code == 401
        body = r.json()
        assert body["success"] is False
        assert body["error"] == "invalid token"


def test_mcp_rejects_wrong_token(data_dir):
    with make_client(data_dir) as c:
        r = c.post("/mcp", headers={"Authorization": "Bearer wrong"},
                   json={"jsonrpc": "2.0", "id": 1, "method": "initialize",
                         "params": {"protocolVersion": "2025-03-26",
                                    "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}})
        assert r.status_code == 401


def test_mcp_accepts_valid_token(data_dir):
    token = "sekrit-token"
    entry = TokenEntry(name="t", token_hash=hashlib.sha256(token.encode()).hexdigest())
    with make_client(data_dir, tokens=[entry]) as c:
        r = c.post("/mcp", headers={"Authorization": f"Bearer {token}"},
                   json={"jsonrpc": "2.0", "id": 1, "method": "initialize",
                         "params": {"protocolVersion": "2025-03-26",
                                    "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}})
        assert r.status_code == 200
        assert "result" in r.json()


def test_mcp_mount_does_not_break_existing_routes(data_dir):
    with make_client(data_dir) as c:
        assert c.get("/healthz").status_code == 200
        assert c.get("/v1/providers").status_code == 401  # 调用方 token 校验仍在
        assert c.get("/api/admin/config").status_code == 401  # admin 会话仍在
```
> 注：initialize 请求体按 MCP 规范；TestClient POST /mcp 走 streamable-http 端点。若 SDK 对 POST 要求特定 header（如 `Content-Type: application/json` 由 TestClient 默认加），按实际调整。

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/pytest tests/test_mcp_auth.py -v`
Expected: FAIL（未挂载 / 无鉴权）

- [ ] **Step 3: 实现鉴权包装与挂载**

按 Interfaces 实现（mcp_server.py 的 `_auth_wrap` + app.py 挂载与 lifespan 共享实例）。

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/pytest tests/test_mcp_auth.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: 全量回归**

Run: `.venv/bin/pytest -v`
Expected: 全绿（153）

- [ ] **Step 6: 提交**

```bash
git add src/searchhub/mcp_server.py src/searchhub/api/app.py tests/test_mcp_auth.py
git commit -m "feat: mount MCP over streamable-http with bearer auth"
```

---

### Task 4: README 文档 + 全量回归 + 冒烟

**Files:**
- Modify: `README.md`

**Interfaces:**
- Produces: README「MCP Server（M3）」章节：
  - 简介：两个工具 `web_search` / `web_extract`；两种传输
  - stdio 用法：`SEARCHHUB_DATA=<数据目录> python -m searchhub.mcp`；MCP 客户端配置示例（JSON）：stdio 方式 command 指向 `python -m searchhub.mcp`，environment 传 SEARCHHUB_DATA；streamable-http 方式 url 指向 `http://<host>:8000/mcp`，headers 带 `Authorization: Bearer <token>`（token 在管理后台创建）
  - 鉴权说明：与调用方 Token 同一体系；无 token 401
  - 验证：`python -m searchhub.mcp` 后用任意 MCP 客户端（如 opencode/claude/cursor）连接测试
- 冒烟：`.venv/bin/python -m searchhub.mcp` 启动 3 秒确认无异常退出（stdio 模式等待输入，超时 kill）——用 `timeout 3` 包裹，退出码 124 即正常（说明一直在等待标准输入）

- [ ] **Step 1: 写 README 章节**

按 Interfaces 追加。

- [ ] **Step 2: stdio 冒烟**

Run: `timeout 3 .venv/bin/python -m searchhub.mcp; echo "exit=$?"`
Expected: `exit=124`（被 timeout 终止，说明 stdio 服务正常待命；非 124 且无 traceback 也接受，以无异常输出为准）

- [ ] **Step 3: 全量回归**

Run: `.venv/bin/pytest -v && cd frontend && npm test`
Expected: pytest 153 全绿 + vitest 17 全绿（前端未改动，仅确认）

- [ ] **Step 4: 提交**

```bash
git add README.md
git commit -m "docs: MCP server usage (stdio + streamable-http)"
```

---

## Self-Review

- **Spec 覆盖**（设计文档 §四 MCP）：streamable-http 挂载 /mcp → Task 3；stdio CLI → Task 1；web_search/web_extract 工具返回单一 JSON 字符串（形状同 REST data）→ Task 1；token 经 Authorization 头 → Task 3；复用引擎/缓存/配置 → Task 1（钩子）+ Task 3（lifespan）。
- **占位符扫描**：无 TBD；Task 1/3 含完整实现代码；Task 2/4 测试与文档内容完整。
- **类型一致性**：`set_engine/_get_engine` 命名在 Task 1 测试与实现一致；`_authorized(config, token)` 复用 M1 的 api/auth.py 函数（签名 `(config: AppConfig, token: str) -> bool`）；`build_mcp_asgi` 在 Task 1 定义、Task 3 改造为带鉴权（共享 MCPServer 实例的说明已写入 Task 3 Interfaces）；`SearchHubEngine.search/extract` 签名与 M2A 一致（含 token_name 关键字参数，MCP 调用不传，默认 ""，历史记录 token_name 为空——可接受，文档注明）。
- 已知取舍：MCP 工具调用不携带调用方身份（token_name 为空串，历史页显示空）；`format` 参数名与 Python 内建同名但合法；stdio 模式 SEARCHHUB_DATA 未设置时用默认 `./data`（与主服务一致）。
- 风险提示：mcp SDK 2.x 客户端/服务端 API 可能随小版本变化——Task 1/2 的测试以安装版本实际 API 为准，偏差需在报告中记录。
