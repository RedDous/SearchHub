# SearchHub M1：核心引擎 + REST API 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 SearchHub 第一里程碑——可独立运行的搜索/提取聚合服务：配置服务、供应商注册表与 6 个 adapter（exa/tavily/ddg/searxng/jina/trafilatura）、Key 池、三种调度策略、合并去重、SQLite 缓存、REST API（hermes 契约形状）。

**Architecture:** Python 3.11+ / FastAPI 单进程。异步引擎：`asyncio.gather` 做 fanout，供应商走 httpx.AsyncClient（云 API 直接调 REST，不依赖各厂商 SDK），ddg/trafilatura 本地库走 `asyncio.to_thread`。配置 `config.yaml` + 密钥 `secrets.env` 由 ConfigService 统一读写，mtime 热重载。存储 SQLite（aiosqlite，WAL），存储层接口化。

**Tech Stack:** fastapi、uvicorn、httpx、pydantic v2、PyYAML、aiosqlite、ddgs、trafilatura；测试 pytest + pytest-asyncio + respx。

## Global Constraints

- Python >= 3.11；依赖版本下限：fastapi>=0.115, uvicorn[standard]>=0.30, httpx>=0.27, pydantic>=2.9, PyYAML>=6.0, aiosqlite>=0.20, ddgs>=9.15, trafilatura>=2.2；dev: pytest>=8, pytest-asyncio>=0.24, respx>=0.21
- 包布局 `src/`，包名 `searchhub`；测试目录 `tests/`，pytest 配置 `asyncio_mode = "auto"`
- 错误形状统一 `{"success": false, "error": str}`；单 URL 提取失败 → 结果数组中该项带 `error` 字段
- 密钥永不出现在日志/API 响应/错误信息中（redaction）
- 供应商响应必须先归一化为统一模型再进入管线
- 所有异步函数必须 async 定义；阻塞库调用一律 `asyncio.to_thread`
- 每个供应商适配器独立文件，注册到 `PROVIDER_CLASSES` 字典
- 提交信息风格：`feat:`, `test:`, `chore:` 前缀（参照仓库现有风格）

## File Structure

```
pyproject.toml
README.md
src/searchhub/
  __init__.py            # __version__ = "0.1.0"
  cli.py                 # python -m searchhub 入口（uvicorn 启动）
  config.py              # ConfigService + AppConfig/ProviderConfig 等配置模型
  models.py              # SearchItem/ExtractItem/SearchResponse/ExtractResponse
  providers/
    __init__.py          # PROVIDER_CLASSES 注册表 + build_registry()
    base.py              # Provider ABC + ProviderError
    keypool.py           # KeyPool（轮转/冷却/并发/限速）
    exa.py               # ExaProvider（search+extract，httpx）
    tavily.py            # TavilyProvider（search+extract，httpx）
    ddg.py               # DdgProvider（search，ddgs 库）
    searxng.py           # SearxngProvider（search，httpx）
    jina.py              # JinaProvider（extract，httpx）
    trafilatura_py.py    # TrafilaturaProvider（extract，本地库）
  engine/
    __init__.py
    rate_limit.py        # TokenBucket（每 key 限速）
    strategies.py        # fanout / rotation / primary_fallback + Outcome
    merge.py             # normalize_url / merge_search / merge_extract
  orchestrator.py        # SearchHubEngine（search/extract 入口）
  storage/
    __init__.py
    db.py                # open_db / init_schema（WAL，schema_version）
    cache.py             # CacheRepo（get/put/delete/touch，TTL）
  api/
    __init__.py
    app.py               # create_app() + lifespan
    auth.py              # require_token 依赖
    routes_health.py     # /healthz /readyz
    routes_search.py     # GET/POST /v1/search
    routes_extract.py    # GET/POST /v1/extract
    routes_providers.py  # GET /v1/providers
tests/
  conftest.py            # data_dir/app/client/engine/fake_provider fixtures
  test_config.py
  providers/test_keypool.py
  providers/test_exa.py
  providers/test_tavily.py
  providers/test_ddg.py
  providers/test_searxng.py
  providers/test_jina.py
  providers/test_trafilatura.py
  providers/test_registry.py
  engine/test_rate_limit.py
  engine/test_strategies.py
  engine/test_merge.py
  storage/test_cache.py
  test_orchestrator.py
  api/test_auth.py
  api/test_search.py
  api/test_extract.py
  api/test_providers.py
  api/test_health.py
```

---

### Task 1: 项目脚手架与 FastAPI 骨架

**Files:**
- Create: `pyproject.toml`
- Create: `README.md`
- Create: `src/searchhub/__init__.py`
- Create: `src/searchhub/__main__.py`
- Create: `src/searchhub/api/__init__.py`
- Create: `src/searchhub/api/app.py`
- Create: `src/searchhub/api/routes_health.py`
- Create: `src/searchhub/cli.py`
- Test: `tests/api/test_health.py`

**Interfaces:**
- Produces: `searchhub.api.app.create_app(data_dir: Path) -> FastAPI`——后续任务挂路由用；`app.state.engine` 供请求依赖取用（Task 15 起）
- Produces: `python -m searchhub` 启动 uvicorn，读环境变量 `SEARCHHUB_DATA`（默认 `./data`）

- [ ] **Step 1: 写 pyproject.toml**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "searchhub"
version = "0.1.0"
description = "Self-hosted web search & extract aggregation service"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "httpx>=0.27",
    "pydantic>=2.9",
    "PyYAML>=6.0",
    "aiosqlite>=0.20",
    "ddgs>=9.15",
    "trafilatura>=2.2",
]

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-asyncio>=0.24", "respx>=0.21"]

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: 安装并确认环境**

Run: `python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"`
Expected: 安装成功无报错

- [ ] **Step 3: 写失败测试**

`tests/api/test_health.py`:
```python
import pytest
from fastapi.testclient import TestClient


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_readyz_returns_ok_when_engine_ready(client):
    r = client.get("/readyz")
    assert r.status_code == 200
    assert r.json() == {"status": "ready"}
```

- [ ] **Step 4: 运行确认失败**

Run: `.venv/bin/pytest tests/api/test_health.py -v`
Expected: FAIL——`searchhub.api.app` 模块不存在

- [ ] **Step 5: 最小实现**

`src/searchhub/__init__.py`:
```python
__version__ = "0.1.0"
```

`src/searchhub/api/app.py`:
```python
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from searchhub.api.routes_health import router as health_router


def create_app(data_dir: Path | None = None) -> FastAPI:
    data_dir = Path(data_dir) if data_dir else Path.cwd() / "data"
    app = FastAPI(title="SearchHub", version="0.1.0")
    app.state.data_dir = data_dir
    app.include_router(health_router)
    return app
```

`src/searchhub/api/routes_health.py`:
```python
from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz():
    return {"status": "ok"}


@router.get("/readyz")
async def readyz():
    return {"status": "ready"}
```

`src/searchhub/cli.py`:
```python
import os

import uvicorn


def main() -> None:
    uvicorn.run(
        "searchhub.api.app:create_app",
        factory=True,
        host=os.environ.get("SEARCHHUB_HOST", "0.0.0.0"),
        port=int(os.environ.get("SEARCHHUB_PORT", "8000")),
    )


if __name__ == "__main__":
    main()
```

`src/searchhub/__main__.py`（支持 `python -m searchhub`）:
```python
from searchhub.cli import main

main()
```

`tests/conftest.py`:
```python
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from searchhub.api.app import create_app


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    return tmp_path / "data"


@pytest.fixture
def app(data_dir: Path):
    return create_app(data_dir)


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c
```

- [ ] **Step 6: 运行确认通过**

Run: `.venv/bin/pytest tests/api/test_health.py -v`
Expected: PASS（2 passed）

- [ ] **Step 7: 提交**

```bash
git add pyproject.toml README.md src tests
git commit -m "chore: scaffold SearchHub M1 (FastAPI skeleton)"
```

---

### Task 2: 配置服务 ConfigService

**Files:**
- Create: `src/searchhub/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces:
  - `class ProviderConfig(BaseModel)`: `id: str`, `capabilities: list[str]`（合法值 `search`/`extract`）, `enabled: bool = True`, `weight: int = 10`, `priority: int = 100`, `max_results: int = 8`, `base_url: str | None = None`, `key_pool: KeyPoolConfig = KeyPoolConfig()`, `options: dict[str, Any] = {}`
  - `class KeyPoolConfig(BaseModel)`: `max_concurrency: int = 2`, `rps_limit: int = 10`, `cooldown_s: float = 60.0`
  - `class AppConfig(BaseModel)`: `strategy: StrategyConfig = StrategyConfig()`, `cache: CacheConfig = CacheConfig()`, `providers: list[ProviderConfig]`
  - `class StrategyConfig`: `default_mode: Literal["fanout", "rotation", "primary_fallback"] = "fanout"`, `timeout_s: float = 15.0`
  - `class CacheConfig`: `enabled: bool = True`, `search_ttl_s: int = 600`, `extract_ttl_s: int = 86400`
  - `class ConfigService`: `__init__(self, data_dir: Path)`; `load(self) -> None`; `get(self) -> AppConfig`; `secrets(self) -> dict[str, str]`; `provider_keys(self, provider_id: str) -> list[str]`; `save_config(self, cfg: AppConfig) -> None`（校验→原子写→滚动备份 5 份）; `maybe_reload(self) -> bool`（mtime 变化才重读，返回是否重载）; `config_version: int`; `data_dir: Path`
- 约定：密钥文件 `secrets.env`，行格式 `PROVIDER_ID_KEY_N=value`（如 `EXA_KEY_1`），N 从 1 起；provider_keys() 按 N 升序返回

- [ ] **Step 1: 写失败测试**

`tests/test_config.py`（完整测试，含默认生成、roundtrip、密钥解析、热重载、备份、校验）：

```python
from pathlib import Path

import pytest

from searchhub.config import AppConfig, ConfigService, ProviderConfig


def test_load_creates_defaults(data_dir: Path):
    cs = ConfigService(data_dir)
    cs.load()
    assert (data_dir / "config.yaml").exists()
    assert (data_dir / "secrets.env").exists()
    cfg = cs.get()
    assert cfg.strategy.default_mode == "fanout"
    assert cfg.cache.search_ttl_s == 600


def test_roundtrip_save(data_dir: Path):
    cs = ConfigService(data_dir)
    cs.load()
    cfg = cs.get()
    cfg.strategy.default_mode = "rotation"
    cfg.providers = [ProviderConfig(id="exa", capabilities=["search", "extract"])]
    cs.save_config(cfg)
    cs2 = ConfigService(data_dir)
    cs2.load()
    assert cs2.get().strategy.default_mode == "rotation"
    assert cs2.get().providers[0].id == "exa"


def test_secrets_parsing(data_dir: Path):
    cs = ConfigService(data_dir)
    cs.load()
    (data_dir / "secrets.env").write_text(
        "EXA_KEY_1=alpha\nEXA_KEY_2=beta\n# comment\nTAVILY_KEY_1=gamma\n"
    )
    cs.maybe_reload()
    assert cs.provider_keys("exa") == ["alpha", "beta"]
    assert cs.provider_keys("tavily") == ["gamma"]
    assert cs.provider_keys("ddg") == []


def test_hot_reload_on_mtime_change(data_dir: Path):
    cs = ConfigService(data_dir)
    cs.load()
    assert not cs.maybe_reload()
    (data_dir / "config.yaml").write_text(
        (data_dir / "config.yaml").read_text() + "\n# touched\n"
    )
    assert cs.maybe_reload()
    assert not cs.maybe_reload()


def test_save_backs_up_previous(data_dir: Path):
    cs = ConfigService(data_dir)
    cs.load()
    cfg = cs.get()
    cs.save_config(cfg)
    cs.save_config(cfg)
    assert len(list(data_dir.glob("config.yaml.bak*"))) >= 1


def test_invalid_yaml_raises(data_dir: Path):
    cs = ConfigService(data_dir)
    cs.load()
    (data_dir / "config.yaml").write_text("strategy: [unclosed")
    with pytest.raises(Exception):
        cs.maybe_reload()


def test_invalid_provider_capability_rejected_on_save(data_dir: Path):
    cs = ConfigService(data_dir)
    cs.load()
    cfg = cs.get()
    cfg.providers = [ProviderConfig(id="exa", capabilities=["search", "crawl"])]
    with pytest.raises(Exception):
        cs.save_config(cfg)
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: FAIL——`searchhub.config` 不存在

- [ ] **Step 3: 实现**

`src/searchhub/config.py`（完整实现）：

```python
from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator

CAPABILITIES = ("search", "extract")
_KEY_LINE = re.compile(r"^([A-Z][A-Z0-9_]*)=(.*)$")
_BACKUP_COUNT = 5


class KeyPoolConfig(BaseModel):
    max_concurrency: int = Field(default=2, ge=1)
    rps_limit: float = Field(default=10, ge=0.1)
    cooldown_s: float = Field(default=60.0, ge=0)


class ProviderConfig(BaseModel):
    id: str
    capabilities: list[str]
    enabled: bool = True
    weight: int = Field(default=10, ge=1, le=100)
    priority: int = Field(default=100, ge=1)
    max_results: int = Field(default=8, ge=1, le=50)
    base_url: str | None = None
    key_pool: KeyPoolConfig = KeyPoolConfig()
    options: dict[str, Any] = {}

    @field_validator("capabilities")
    @classmethod
    def _check_capabilities(cls, v: list[str]) -> list[str]:
        for c in v:
            if c not in CAPABILITIES:
                raise ValueError(f"invalid capability: {c!r}")
        return v


class StrategyConfig(BaseModel):
    default_mode: Literal["fanout", "rotation", "primary_fallback"] = "fanout"
    timeout_s: float = Field(default=15.0, ge=0.5, le=120)


class CacheConfig(BaseModel):
    enabled: bool = True
    search_ttl_s: int = Field(default=600, ge=0)
    extract_ttl_s: int = Field(default=86400, ge=0)


class AppConfig(BaseModel):
    strategy: StrategyConfig = StrategyConfig()
    cache: CacheConfig = CacheConfig()
    providers: list[ProviderConfig] = Field(default_factory=list)

    def provider(self, provider_id: str) -> ProviderConfig | None:
        return next((p for p in self.providers if p.id == provider_id), None)


class ConfigService:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.config_path = self.data_dir / "config.yaml"
        self.secrets_path = self.data_dir / "secrets.env"
        self._cfg = AppConfig()
        self._secrets: dict[str, str] = {}
        self._loaded = False
        self._mtime: tuple[float, float] = (-1.0, -1.0)
        self.config_version = 0

    def load(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if not self.config_path.exists():
            self._cfg = AppConfig()
            self._write_yaml(self._cfg)
        else:
            self._cfg = AppConfig.model_validate(
                yaml.safe_load(self.config_path.read_text()) or {}
            )
        self._secrets = self._parse_secrets()
        self._mtime = self._stat()
        self._loaded = True

    def get(self) -> AppConfig:
        if not self._loaded:
            self.load()
        return self._cfg

    def secrets(self) -> dict[str, str]:
        return self._secrets

    def provider_keys(self, provider_id: str) -> list[str]:
        prefix = f"{provider_id.upper()}_KEY_"
        pairs = [
            (int(k[len(prefix):]), v)
            for k, v in self._secrets.items()
            if k.startswith(prefix) and k[len(prefix):].isdigit()
        ]
        return [v for _, v in sorted(pairs)]

    def save_config(self, cfg: AppConfig) -> None:
        self._cfg = cfg
        self._write_yaml(cfg)

    def maybe_reload(self) -> bool:
        if not self._loaded:
            self.load()
            return True
        if self._stat() != self._mtime:
            self.load()
            return True
        return False

    def _stat(self) -> tuple[float, float]:
        def m(p: Path) -> float:
            try:
                return p.stat().st_mtime_ns
            except FileNotFoundError:
                return -1.0

        return (m(self.config_path), m(self.secrets_path))

    def _write_yaml(self, cfg: AppConfig) -> None:
        if self.config_path.exists():
            for i in range(_BACKUP_COUNT - 1, 0, -1):
                src = self.config_path.with_suffix(f".bak{i}")
                dst = self.config_path.with_suffix(f".bak{i + 1}")
                if src.exists():
                    shutil.move(str(src), str(dst))
            shutil.copy2(self.config_path, self.config_path.with_suffix(".bak1"))
        raw = cfg.model_dump(mode="json")
        yaml.safe_dump(raw, self.config_path.open("w"), allow_unicode=True, sort_keys=False)
        self.config_version += 1
        self._mtime = self._stat()

    def _parse_secrets(self) -> dict[str, str]:
        if not self.secrets_path.exists():
            self.secrets_path.touch(mode=0o600)
            return {}
        result: dict[str, str] = {}
        for line in self.secrets_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = _KEY_LINE.match(line)
            if m:
                result[m.group(1)] = m.group(2)
        return result
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: PASS（7 passed）

- [ ] **Step 5: 提交**

```bash
git add src/searchhub/config.py tests/test_config.py
git commit -m "feat: config service with yaml + secrets, hot reload, backups"
```

---

### Task 3: TokenBucket 限速器

**Files:**
- Create: `src/searchhub/engine/__init__.py`
- Create: `src/searchhub/engine/rate_limit.py`
- Test: `tests/engine/test_rate_limit.py`

**Interfaces:**
- Produces: `class TokenBucket`: `__init__(self, rate: float, capacity: float | None = None)`；`async def acquire(self, n: int = 1) -> None`（按需 sleep 到令牌充足）；`rate` 属性

- [ ] **Step 1: 写失败测试**

`tests/engine/test_rate_limit.py`:
```python
import asyncio
import time

import pytest

from searchhub.engine.rate_limit import TokenBucket


@pytest.mark.asyncio
async def test_allows_up_to_rate():
    bucket = TokenBucket(rate=10)
    start = time.monotonic()
    for _ in range(10):
        await bucket.acquire()
    elapsed = time.monotonic() - start
    assert elapsed < 0.5


@pytest.mark.asyncio
async def test_throttles_beyond_rate():
    bucket = TokenBucket(rate=5)
    for _ in range(5):
        await bucket.acquire()
    start = time.monotonic()
    await bucket.acquire()
    elapsed = time.monotonic() - start
    assert elapsed >= 0.15


@pytest.mark.asyncio
async def test_parallel_acquisitions_are_serialized():
    bucket = TokenBucket(rate=4, capacity=1)
    start = time.monotonic()
    await asyncio.gather(*(bucket.acquire() for _ in range(4)))
    elapsed = time.monotonic() - start
    assert elapsed >= 0.6
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/pytest tests/engine/test_rate_limit.py -v`
Expected: FAIL——模块不存在

- [ ] **Step 3: 实现**

`src/searchhub/engine/rate_limit.py`:
```python
from __future__ import annotations

import asyncio
import time


class TokenBucket:
    """简易异步令牌桶：rate 个令牌/秒，超限时 acquire 睡眠等待。"""

    def __init__(self, rate: float, capacity: float | None = None):
        if rate <= 0:
            raise ValueError("rate must be > 0")
        self.rate = rate
        self.capacity = capacity if capacity is not None else rate
        self._tokens = float(self.capacity)
        self._updated = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, n: int = 1) -> None:
        while True:
            async with self._lock:
                now = time.monotonic()
                self._tokens = min(self.capacity, self._tokens + (now - self._updated) * self.rate)
                self._updated = now
                if self._tokens >= n:
                    self._tokens -= n
                    return
                deficit = n - self._tokens
                wait = deficit / self.rate
            await asyncio.sleep(wait)
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/pytest tests/engine/test_rate_limit.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: 提交**

```bash
git add src/searchhub/engine tests/engine/test_rate_limit.py
git commit -m "feat: async token bucket rate limiter"
```

---

### Task 4: KeyPool（轮转/冷却/并发/限速）

**Files:**
- Create: `src/searchhub/providers/__init__.py`（仅占位，注册表在 Task 5）
- Create: `src/searchhub/providers/keypool.py`
- Test: `tests/providers/test_keypool.py`

**Interfaces:**
- Produces: `class KeyPool`: `__init__(self, keys: list[str], max_concurrency: int = 2, rps_limit: float = 10, cooldown_s: float = 60.0)`；`@asynccontextmanager async def use(self) -> AsyncIterator[str]`（获取一个可用 key，退出时释放；无可用 key 时等待）; `report_error(self, key: str, status: int | None = None) -> None`（429/432→cooldown_s；401/403→cooldown_s*10；其他→min(5, cooldown_s)）；`status(self) -> list[dict]`（每 key：`{key: 掩码, cooling_until, in_flight, ok}`）

- [ ] **Step 1: 写失败测试**

`tests/providers/test_keypool.py`:
```python
import asyncio
import time

import pytest

from searchhub.providers.keypool import KeyPool


@pytest.mark.asyncio
async def test_round_robin_order():
    pool = KeyPool(keys=["a", "b", "c"])
    seen = []
    for _ in range(6):
        async with pool.use() as key:
            seen.append(key)
    assert seen == ["a", "b", "c", "a", "b", "c"]


@pytest.mark.asyncio
async def test_error_puts_key_in_cooldown():
    pool = KeyPool(keys=["a", "b"], cooldown_s=60)
    async with pool.use() as key:
        pool.report_error(key, status=429)
    used = set()
    for _ in range(4):
        async with pool.use() as k:
            used.add(k)
    assert used == {"b"}


@pytest.mark.asyncio
async def test_concurrency_limited():
    pool = KeyPool(keys=["a"], max_concurrency=1)
    async def slow():
        async with pool.use():
            await asyncio.sleep(0.2)
    start = time.monotonic()
    await asyncio.gather(slow(), slow())
    assert time.monotonic() - start >= 0.35


@pytest.mark.asyncio
async def test_status_masks_key():
    pool = KeyPool(keys=["tvly-secret123"])
    async with pool.use():
        pass
    st = pool.status()[0]
    assert st["key"] != "tvly-secret123"
    assert st["key"].startswith("tvly-") and "****" in st["key"]
    assert st["ok"] is True
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/pytest tests/providers/test_keypool.py -v`
Expected: FAIL——模块不存在

- [ ] **Step 3: 实现**

`src/searchhub/providers/keypool.py`:
```python
from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator

from searchhub.engine.rate_limit import TokenBucket


class _KeyState:
    def __init__(self, key: str, max_concurrency: int, rps_limit: float, cooldown_s: float):
        self.key = key
        self.max_concurrency = max_concurrency
        self.sem = asyncio.Semaphore(max_concurrency)
        self.bucket = TokenBucket(rps_limit)
        self.cooldown_s = cooldown_s
        self.cooldown_until = 0.0
        self.in_flight = 0
        self.ok = True


class KeyPool:
    def __init__(self, keys: list[str], max_concurrency: int = 2,
                 rps_limit: float = 10, cooldown_s: float = 60.0):
        self._keys = [_KeyState(k, max_concurrency, rps_limit, cooldown_s) for k in keys]
        self._cursor = 0
        self._free_event = asyncio.Event()
        self._free_event.set()

    @asynccontextmanager
    async def use(self) -> AsyncIterator[str]:
        key = await self._acquire()
        try:
            yield key.key
        finally:
            key.in_flight -= 1
            key.sem.release()
            self._free_event.set()

    async def _acquire(self) -> _KeyState:
        while True:
            state = self._pick()
            if state is not None:
                await state.sem.acquire()
                await state.bucket.acquire()
                state.in_flight += 1
                return state
            self._free_event.clear()
            await asyncio.wait_for(self._free_event.wait(), timeout=5.0)
            self._free_event.set()

    def _pick(self) -> _KeyState | None:
        n = len(self._keys)
        if n == 0:
            return None
        now = time.monotonic()
        for _ in range(n):
            state = self._keys[self._cursor % n]
            self._cursor += 1
            if state.cooldown_until <= now and state.sem._value > 0:
                return state
        return None

    def report_error(self, key: str, status: int | None = None) -> None:
        for state in self._keys:
            if state.key == key:
                if status in (429, 432):
                    state.cooldown_until = time.monotonic() + state.cooldown_s
                elif status in (401, 403):
                    state.cooldown_until = time.monotonic() + state.cooldown_s * 10
                    state.ok = False
                else:
                    state.cooldown_until = time.monotonic() + min(5.0, state.cooldown_s)
                return

    def status(self) -> list[dict]:
        now = time.monotonic()
        result = []
        for state in self._keys:
            mask = state.key[:8] + "****" + state.key[-4:]
            result.append({
                "key": mask,
                "cooling_until": max(0.0, state.cooldown_until - now),
                "in_flight": state.in_flight,
                "ok": state.ok and state.cooldown_until <= now,
            })
        return result
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/pytest tests/providers/test_keypool.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: 提交**

```bash
git add src/searchhub/providers/keypool.py tests/providers/test_keypool.py
git commit -m "feat: per-provider key pool with round-robin, cooldown, concurrency, rps"
```

---

### Task 5: Provider 基类与注册表

**Files:**
- Create: `src/searchhub/providers/base.py`
- Modify: `src/searchhub/providers/__init__.py`
- Create: `src/searchhub/providers/exa.py`（占位 stub，Task 7 填充）
- Test: `tests/providers/test_registry.py`

**Interfaces:**
- Produces: `class ProviderError(Exception)`: `__init__(self, provider_id: str, message: str, status: int | None = None)`
- Produces: `class Provider(ABC)`: 类属性 `id: str`、`capabilities: frozenset[str]`；实例属性 `cfg: ProviderConfig`、`keys: list[str]`、`http: httpx.AsyncClient`、`key_pool: KeyPool | None`（有 key 才有）；方法 `supports(self, cap: str) -> bool`；抽象 `async def search(self, query: str, limit: int) -> list[SearchItem]`；抽象 `async def extract(self, urls: list[str], *, fmt: str = "markdown", max_chars: int = 15000) -> list[ExtractItem]`
- Produces: `searchhub.providers.PROVIDER_CLASSES: dict[str, type[Provider]]`（Task 7-11 逐个注册）；`def build_registry(cfg: AppConfig, secrets: dict[str, str], http: httpx.AsyncClient) -> dict[str, Provider]`——按 config.providers 实例化启用的适配器；`def registry_for_capability(registry, cap: str) -> list[Provider]`（按 priority 升序）
- `models.py`（本任务实现，供 base.py 用）：
  - `class SearchItem(BaseModel)`: `title: str`, `url: str`, `description: str = ""`, `position: int = 0`, `provider: str = ""`, `score: float = 0.0`, `published_at: str | None = None`
  - `class ExtractItem(BaseModel)`: `url: str`, `title: str = ""`, `content: str = ""`, `raw_content: str = ""`, `metadata: dict[str, Any] = {}`, `provider: str = ""`, `error: str | None = None`
  - `class SearchData(BaseModel)`: `web: list[SearchItem]`
  - `class SearchResponse(BaseModel)`: `success: bool = True`, `data: SearchData`, `meta: dict[str, Any] = {}`
  - `class ExtractResponse(BaseModel)`: `success: bool = True`, `data: list[ExtractItem]`, `meta: dict[str, Any] = {}`

- [ ] **Step 1: 写失败测试**

`tests/providers/test_registry.py`:
```python
import httpx
import pytest

from searchhub.config import AppConfig, ConfigService, ProviderConfig
from searchhub.providers import build_registry, registry_for_capability


@pytest.fixture
def cfg(data_dir) -> AppConfig:
    cs = ConfigService(data_dir)
    cs.load()
    cfg = cs.get()
    cfg.providers = [
        ProviderConfig(id="ddg", capabilities=["search"], weight=5, priority=1),
        ProviderConfig(id="exa", capabilities=["search", "extract"], weight=10, priority=2),
        ProviderConfig(id="unknown-thing", capabilities=["search"]),
    ]
    return cfg


def test_build_registry_instantiates_enabled(cfg):
    http = httpx.AsyncClient()
    registry = build_registry(cfg, {"EXA_KEY_1": "k1"}, http)
    assert set(registry) == {"ddg", "exa"}


def test_unknown_provider_id_is_skipped(cfg):
    http = httpx.AsyncClient()
    registry = build_registry(cfg, {}, http)
    assert "unknown-thing" not in registry


def test_registry_for_capability_orders_by_priority(cfg):
    http = httpx.AsyncClient()
    registry = build_registry(cfg, {"EXA_KEY_1": "k1"}, http)
    assert [p.id for p in registry_for_capability(registry, "search")] == ["ddg", "exa"]
    assert [p.id for p in registry_for_capability(registry, "extract")] == ["exa"]


def test_cloud_provider_without_key_is_skipped(cfg):
    cfg.providers = [ProviderConfig(id="exa", capabilities=["search"])]
    http = httpx.AsyncClient()
    registry = build_registry(cfg, {}, http)
    assert "exa" not in registry
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/pytest tests/providers/test_registry.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 models 与 base**

`src/searchhub/models.py`:
```python
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class SearchItem(BaseModel):
    title: str
    url: str
    description: str = ""
    position: int = 0
    provider: str = ""
    score: float = 0.0
    published_at: str | None = None


class ExtractItem(BaseModel):
    url: str
    title: str = ""
    content: str = ""
    raw_content: str = ""
    metadata: dict[str, Any] = {}
    provider: str = ""
    error: str | None = None


class SearchData(BaseModel):
    web: list[SearchItem]


class SearchResponse(BaseModel):
    success: bool = True
    data: SearchData
    meta: dict[str, Any] = {}
    error: str | None = None


class ExtractResponse(BaseModel):
    success: bool = True
    data: list[ExtractItem]
    meta: dict[str, Any] = {}
    error: str | None = None
```

`src/searchhub/providers/base.py`:
```python
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import httpx

from searchhub.config import ProviderConfig
from searchhub.models import ExtractItem, SearchItem
from searchhub.providers.keypool import KeyPool


class ProviderError(Exception):
    def __init__(self, provider_id: str, message: str, status: int | None = None):
        super().__init__(message)
        self.provider_id = provider_id
        self.message = message
        self.status = status


class Provider(ABC):
    id: str = ""
    capabilities: frozenset[str] = frozenset()

    def __init__(self, cfg: ProviderConfig, keys: list[str], http: httpx.AsyncClient):
        self.cfg = cfg
        self.keys = keys
        self.http = http
        if keys:
            self.key_pool = KeyPool(
                keys,
                max_concurrency=cfg.key_pool.max_concurrency,
                rps_limit=cfg.key_pool.rps_limit,
                cooldown_s=cfg.key_pool.cooldown_s,
            )
        else:
            self.key_pool = None

    def supports(self, cap: str) -> bool:
        return cap in self.capabilities

    @abstractmethod
    async def search(self, query: str, limit: int) -> list[SearchItem]: ...

    @abstractmethod
    async def extract(self, urls: list[str], *, fmt: str = "markdown",
                      max_chars: int = 15000) -> list[ExtractItem]: ...

    def truncate(self, text: str, max_chars: int) -> str:
        return text[:max_chars] if max_chars and len(text) > max_chars else text
```

- [ ] **Step 4: 实现注册表**

`src/searchhub/providers/__init__.py`:
```python
from __future__ import annotations

import logging

import httpx

from searchhub.config import AppConfig
from searchhub.providers.base import Provider

log = logging.getLogger(__name__)

PROVIDER_CLASSES: dict[str, type[Provider]] = {}


def build_registry(cfg: AppConfig, secrets: dict[str, str],
                   http: httpx.AsyncClient) -> dict[str, Provider]:
    registry: dict[str, Provider] = {}
    for pc in cfg.providers:
        if not pc.enabled:
            continue
        cls = PROVIDER_CLASSES.get(pc.id)
        if cls is None:
            log.warning("provider %s: unknown adapter class, skipped", pc.id)
            continue
        keys = [secrets[k] for k in sorted(
            (k for k in secrets if k.startswith(f"{pc.id.upper()}_KEY_") and k.rsplit("_", 1)[-1].isdigit()),
            key=lambda k: int(k.rsplit("_", 1)[-1]),
        )]
        if pc.capabilities and cls.REQUIRES_KEY and not keys:
            log.warning("provider %s: no API key configured, skipped", pc.id)
            continue
        registry[pc.id] = cls(pc, keys, http)
    return registry


def registry_for_capability(registry: dict[str, Provider], cap: str) -> list[Provider]:
    return sorted(
        (p for p in registry.values() if p.supports(cap)),
        key=lambda p: p.cfg.priority,
    )
```

`src/searchhub/providers/exa.py`（本任务占位，Task 7 填充完整实现；REQUIRES_KEY 类属性现在就定）:
```python
from __future__ import annotations

from searchhub.providers.base import Provider


class ExaProvider(Provider):
    id = "exa"
    capabilities = frozenset({"search", "extract"})
    REQUIRES_KEY = True
```

（tavily.py/ddg.py/searxng.py/jina.py/trafilatura_py.py 同占位，各自 REQUIRES_KEY：tavily=True、ddg=False、searxng=False、jina=False、trafilatura=False，本任务一并创建并在 PROVIDER_CLASSES 注册——注意 import 空实现类必须放在 PROVIDER_CLASSES 定义之后）

`src/searchhub/providers/__init__.py` 末尾追加：
```python
from searchhub.providers import base  # noqa: F401  (ensure abstract base loaded)
from searchhub.providers.ddg import DdgProvider
from searchhub.providers.exa import ExaProvider
from searchhub.providers.jina import JinaProvider
from searchhub.providers.searxng import SearxngProvider
from searchhub.providers.tavily import TavilyProvider
from searchhub.providers.trafilatura_py import TrafilaturaProvider

PROVIDER_CLASSES.update({
    "exa": ExaProvider,
    "tavily": TavilyProvider,
    "ddg": DdgProvider,
    "searxng": SearxngProvider,
    "jina": JinaProvider,
    "trafilatura": TrafilaturaProvider,
})
```

- [ ] **Step 5: 运行确认通过**

Run: `.venv/bin/pytest tests/providers/test_registry.py -v`
Expected: PASS（4 passed）

- [ ] **Step 6: 提交**

```bash
git add src/searchhub/models.py src/searchhub/providers tests/providers/test_registry.py
git commit -m "feat: provider base class, registry, unified data models"
```

---

### Task 6: 合并与去重（merge）

**Files:**
- Create: `src/searchhub/engine/merge.py`
- Test: `tests/engine/test_merge.py`

**Interfaces:**
- Produces: `normalize_url(url: str) -> str`（去 `#fragment`、`utm_*`/`fbclid`/`gclid` query、尾部斜杠、http/https 归一）
- Produces: `merge_search(outcomes: list[Outcome], limit: int, providers: dict[str, Provider]) -> list[SearchItem]`——Outcome 见 Task 7；对成功 outcome 的 items 规范化 URL 去重（保留 weight 最高者，同 URL 的 title/description 取更长的）；按 `score = weight * (1 - position/50)` 降序；截断到 limit
- Produces: `merge_extract(outcomes: list[Outcome], urls: list[str], providers: dict[str, Provider]) -> list[ExtractItem]`——每个 URL 取 weight 最高且成功的来源；全部失败 → 该 URL 产生 `ExtractItem(error=...)`；输出顺序 = urls 传入顺序

- [ ] **Step 1: 写失败测试**

`tests/engine/test_merge.py`:
```python
from searchhub.config import ProviderConfig
from searchhub.engine.merge import merge_extract, merge_search, normalize_url
from searchhub.engine.strategies import Outcome
from searchhub.models import ExtractItem, SearchItem
from searchhub.providers.base import Provider


def make_provider(pid, weight):
    p = Provider.__new__(Provider)
    p.id = pid
    p.cfg = ProviderConfig(id=pid, capabilities=["search"], weight=weight)
    return p


def test_normalize_url():
    assert normalize_url("HTTP://Example.com/path/") == "http://example.com/path"
    assert normalize_url("https://a.com/x?utm_source=1&q=2#top") == "https://a.com/x?q=2"
    assert normalize_url("https://a.com/x?fbclid=abc") == "https://a.com/x"


def test_merge_search_dedups_and_ranks():
    low = make_provider("ddg", 5)
    high = make_provider("exa", 10)
    items_low = [SearchItem(title="t", url="https://a.com/x", position=0, provider="ddg")]
    items_high = [
        SearchItem(title="better title here", url="https://a.com/x", position=0, provider="exa"),
        SearchItem(title="unique", url="https://b.com", position=1, provider="exa"),
    ]
    merged = merge_search(
        [Outcome("ddg", items_low), Outcome("exa", items_high)], limit=5,
        {"ddg": low, "exa": high},
    )
    assert len(merged) == 2
    assert merged[0].url == "https://a.com/x"  # 去重后保留高权重来源，且位置靠前得分最高
    assert merged[0].provider == "exa"
    assert merged[0].title == "better title here"
    assert merged[1].url == "https://b.com"


def test_merge_search_truncates_to_limit():
    prov = make_provider("exa", 10)
    items = [SearchItem(title=str(i), url=f"https://a.com/{i}", position=i, provider="exa") for i in range(5)]
    merged = merge_search([Outcome("exa", items)], limit=2, {"exa": prov})
    assert len(merged) == 2


def test_merge_extract_picks_best_provider_per_url():
    low = make_provider("jina", 5)
    high = make_provider("exa", 10)
    outcomes = [
        Outcome("jina", [ExtractItem(url="https://a.com", content="short", provider="jina")]),
        Outcome("exa", [ExtractItem(url="https://a.com", content="full content", provider="exa"),
                        ExtractItem(url="https://b.com", content="b", provider="exa")]),
    ]
    merged = merge_extract(outcomes, ["https://a.com", "https://b.com"], {"jina": low, "exa": high})
    assert [m.url for m in merged] == ["https://a.com", "https://b.com"]
    assert merged[0].provider == "exa"
    assert merged[1].content == "b"


def test_merge_extract_error_item_when_all_fail():
    prov = make_provider("jina", 5)
    outcomes = [Outcome("jina", None, error="boom")]
    merged = merge_extract(outcomes, ["https://a.com"], {"jina": prov})
    assert merged[0].error == "boom"
    assert merged[0].url == "https://a.com"
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/pytest tests/engine/test_merge.py -v`
Expected: FAIL——`engine.strategies.Outcome` 不存在（Task 7 会建，本任务先建 Outcome 的最小版：`@dataclass Outcome: provider_id: str; items: list | None = None; error: str | None = None; took_ms: float = 0.0; cache_hit: bool = False`，放 `engine/strategies.py`）

- [ ] **Step 3: 实现**

`src/searchhub/engine/merge.py`:
```python
from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from searchhub.engine.strategies import Outcome
from searchhub.models import ExtractItem, SearchItem
from searchhub.providers.base import Provider

_TRACKING = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid"}


def normalize_url(url: str) -> str:
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    netloc = parts.netloc.lower()
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k.lower() not in _TRACKING]
    path = parts.path.rstrip("/")
    return urlunsplit((scheme, netloc, path, urlencode(query), ""))


def _weight(providers: dict[str, Provider], pid: str) -> int:
    p = providers.get(pid)
    return p.cfg.weight if p else 1


def merge_search(outcomes: list[Outcome], limit: int,
                 providers: dict[str, Provider]) -> list[SearchItem]:
    best: dict[str, SearchItem] = {}
    for out in outcomes:
        if out.error or not out.items:
            continue
        w = _weight(providers, out.provider_id)
        for item in out.items:
            key = normalize_url(item.url)
            prev = best.get(key)
            if prev is None or _weight(providers, prev.provider) < w:
                item.score = w * (1 - min(item.position, 49) / 50)
                best[key] = item
            elif prev and len(prev.title) < len(item.title) and prev.provider == item.provider:
                best[key] = item
    ranked = sorted(best.values(), key=lambda i: i.score, reverse=True)
    return ranked[:limit]


def merge_extract(outcomes: list[Outcome], urls: list[str],
                  providers: dict[str, Provider]) -> list[ExtractItem]:
    by_url: dict[str, ExtractItem] = {}
    for out in outcomes:
        if out.error or not out.items:
            continue
        w = _weight(providers, out.provider_id)
        for item in out.items:
            prev = by_url.get(item.url)
            if prev is None or _weight(providers, prev.provider) < w:
                by_url[item.url] = item
    result: list[ExtractItem] = []
    for url in urls:
        item = by_url.get(url)
        if item is None:
            result.append(ExtractItem(url=url, error="all providers failed"))
        else:
            result.append(item)
    return result
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/pytest tests/engine/test_merge.py -v`
Expected: PASS（5 passed）

- [ ] **Step 5: 提交**

```bash
git add src/searchhub/engine/merge.py src/searchhub/engine/strategies.py tests/engine/test_merge.py
git commit -m "feat: result merge, dedup and ranking"
```

---

### Task 7: 策略（fanout / rotation / primary_fallback）

**Files:**
- Modify: `src/searchhub/engine/strategies.py`
- Test: `tests/engine/test_strategies.py`

**Interfaces:**
- Produces: `@dataclass Outcome`: `provider_id: str; items: list | None = None; error: str | None = None; took_ms: float = 0.0; cache_hit: bool = False`
- Produces:
  - `async def fanout(calls: list[tuple[Provider, Coroutine]], timeout_s: float) -> list[Outcome]`——`asyncio.gather(return_exceptions=True)`，单项超时用 `asyncio.wait_for`，超时/ProviderError/其他异常 → Outcome(error)
  - `async def rotation(providers: list[Provider], cap: str, timeout_s: float, call) -> Outcome`——轮转 cursor（模块级 `_ROTATION_CURSOR: dict[str, int]`），逐个尝试，成功即返回；全失败返回最后一个错误
  - `async def primary_fallback(providers: list[Provider], cap: str, timeout_s: float, call) -> Outcome`——按传入顺序（已按 priority 排好）第一个成功即返回
  - `call` 签名统一为 `async def call(p: Provider) -> list[SearchItem] | list[ExtractItem]`

- [ ] **Step 1: 写失败测试**

`tests/engine/test_strategies.py`:
```python
import asyncio

import pytest

from searchhub.engine.strategies import Outcome, fanout, primary_fallback, rotation
from searchhub.providers.base import ProviderError


class FakeProvider:
    def __init__(self, pid, fail=False, slow=0, items=None):
        self.id = pid
        self.fail = fail
        self.slow = slow
        self.items = items if items is not None else [{"url": pid}]

    async def call(self):
        if self.fail:
            raise ProviderError(self.id, "boom", status=500)
        if self.slow:
            await asyncio.sleep(self.slow)
        return self.items


@pytest.mark.asyncio
async def test_fanout_returns_all_outcomes():
    calls = [(p, p.call()) for p in [FakeProvider("a"), FakeProvider("b", fail=True)]]
    outcomes = await fanout(calls, timeout_s=5)
    assert {o.provider_id: o.error is None for o in outcomes} == {"a": True, "b": False}
    assert outcomes[0].items == [{"url": "a"}]


@pytest.mark.asyncio
async def test_fanout_slow_provider_times_out_independently():
    calls = [(p, p.call()) for p in [FakeProvider("a", slow=1), FakeProvider("b")]]
    outcomes = await fanout(calls, timeout_s=0.1)
    by_id = {o.provider_id: o for o in outcomes}
    assert by_id["a"].error is not None
    assert by_id["b"].items == [{"url": "b"}]


@pytest.mark.asyncio
async def test_rotation_skips_failing_and_advances_cursor():
    outcomes = []
    for _ in range(2):
        o = await rotation(
            [FakeProvider("a", fail=True), FakeProvider("b")], "search", 1.0,
            lambda p: p.call(),
        )
        outcomes.append(o.provider_id)
    assert outcomes == ["b", "b"]


@pytest.mark.asyncio
async def test_rotation_all_fail_returns_error():
    o = await rotation([FakeProvider("a", fail=True)], "search", 1.0, lambda p: p.call())
    assert o.error is not None


@pytest.mark.asyncio
async def test_primary_fallback_first_success_wins():
    o = await primary_fallback(
        [FakeProvider("a"), FakeProvider("b")], "search", 1.0, lambda p: p.call(),
    )
    assert o.provider_id == "a"


@pytest.mark.asyncio
async def test_primary_fallback_falls_through():
    o = await primary_fallback(
        [FakeProvider("a", fail=True), FakeProvider("b")], "search", 1.0,
        lambda p: p.call(),
    )
    assert o.provider_id == "b"
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/pytest tests/engine/test_strategies.py -v`
Expected: FAIL——`fanout`/`rotation`/`primary_fallback` 未定义

- [ ] **Step 3: 实现**

`src/searchhub/engine/strategies.py`（完整内容，覆盖 Task 6 引入的 Outcome）:
```python
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

from searchhub.providers.base import Provider, ProviderError


@dataclass
class Outcome:
    provider_id: str
    items: list | None = None
    error: str | None = None
    took_ms: float = 0.0
    cache_hit: bool = False

    @classmethod
    def error_outcome(cls, provider_id: str, err: BaseException, took_ms: float = 0.0) -> "Outcome":
        if isinstance(err, ProviderError):
            message = err.message
        elif isinstance(err, TimeoutError):
            message = "provider timeout"
        else:
            message = str(err) or err.__class__.__name__
        return cls(provider_id=provider_id, error=message, took_ms=took_ms)


async def fanout(calls: list[tuple[Provider, Coroutine]], timeout_s: float) -> list[Outcome]:
    async def run(p: Provider, coro: Coroutine) -> Outcome:
        start = time.monotonic()
        try:
            items = await asyncio.wait_for(coro, timeout=timeout_s)
            return Outcome(provider_id=p.id, items=items, took_ms=(time.monotonic() - start) * 1000)
        except BaseException as e:
            return Outcome.error_outcome(p.id, e, (time.monotonic() - start) * 1000)

    return await asyncio.gather(*(run(p, c) for p, c in calls))


_ROTATION_CURSOR: dict[str, int] = {}


async def rotation(providers: list[Provider], cap: str, timeout_s: float,
                   call: Callable[[Provider], Coroutine]) -> Outcome:
    if not providers:
        return Outcome(provider_id="", error="no provider available")
    cursor = _ROTATION_CURSOR.get(cap, 0)
    last: Outcome = Outcome(provider_id="", error="no provider available")
    for i in range(len(providers)):
        p = providers[(cursor + i) % len(providers)]
        start = time.monotonic()
        try:
            items = await asyncio.wait_for(call(p), timeout=timeout_s)
            outcome = Outcome(provider_id=p.id, items=items,
                              took_ms=(time.monotonic() - start) * 1000)
            _ROTATION_CURSOR[cap] = (cursor + i + 1) % len(providers)
            return outcome
        except BaseException as e:
            last = Outcome.error_outcome(p.id, e, (time.monotonic() - start) * 1000)
    _ROTATION_CURSOR[cap] = (cursor + len(providers)) % len(providers)
    return last


async def primary_fallback(providers: list[Provider], cap: str, timeout_s: float,
                           call: Callable[[Provider], Coroutine]) -> Outcome:
    if not providers:
        return Outcome(provider_id="", error="no provider available")
    last: Outcome = Outcome(provider_id="", error="no provider available")
    for p in providers:
        start = time.monotonic()
        try:
            items = await asyncio.wait_for(call(p), timeout=timeout_s)
            return Outcome(provider_id=p.id, items=items,
                           took_ms=(time.monotonic() - start) * 1000)
        except BaseException as e:
            last = Outcome.error_outcome(p.id, e, (time.monotonic() - start) * 1000)
    return last
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/pytest tests/engine/test_merge.py tests/engine/test_strategies.py -v`
Expected: PASS（6 + 5 passed）

- [ ] **Step 5: 提交**

```bash
git add src/searchhub/engine/strategies.py tests/engine/test_strategies.py
git commit -m "feat: dispatch strategies (fanout, rotation, primary_fallback)"
```

---

### Task 8: Adapter — exa（search + extract）

**Files:**
- Modify: `src/searchhub/providers/exa.py`（替换占位）
- Test: `tests/providers/test_exa.py`

**Interfaces:**
- Consumes: `Provider`（base.py）、`ProviderError`、KeyPool.use()
- Produces: `ExaProvider.search(query, limit)` 调 `POST https://api.exa.ai/search`，body `{"query", "num_results": limit, "type": "auto", "contents": {"text": true}}`，header `x-api-key`；映射 `results[]` → `SearchItem(title, url, description=text[:300], position, published_at=publishedDate)`
- Produces: `ExaProvider.extract(urls, fmt="markdown", max_chars=15000)` 调 `POST https://api.exa.ai/contents`，body `{"urls": [...], "text": true}`；映射 `results[]` → `ExtractItem(url, title, raw_content=text, content=truncate(text, max_chars))`；`failedResults[]`（`{url, error}`）→ `ExtractItem(error=...)`
- 错误处理：非 2xx → `ProviderError(id, 摘要, status)`；KeyPool 状态上报

- [ ] **Step 1: 写失败测试**

`tests/providers/test_exa.py`（respx mock httpx）:
```python
import httpx
import respx
import pytest

from searchhub.config import ProviderConfig
from searchhub.providers.base import ProviderError
from searchhub.providers.exa import ExaProvider

EXA = "https://api.exa.ai"


def make_provider():
    cfg = ProviderConfig(id="exa", capabilities=["search", "extract"])
    return ExaProvider(cfg, ["k1"], httpx.AsyncClient())


@pytest.mark.asyncio
@respx.mock
async def test_search_maps_results():
    respx.post(f"{EXA}/search").mock(return_value=httpx.Response(200, json={
        "results": [
            {"title": "T1", "url": "https://a.com", "text": "some text body", "publishedDate": "2024-01-01"},
        ]
    }))
    items = await make_provider().search("python", 3)
    assert len(items) == 1
    assert items[0].title == "T1"
    assert items[0].url == "https://a.com"
    assert items[0].description == "some text body"
    assert items[0].published_at == "2024-01-01"
    assert items[0].provider == "exa"


@pytest.mark.asyncio
@respx.mock
async def test_search_429_raises_provider_error():
    respx.post(f"{EXA}/search").mock(return_value=httpx.Response(429, json={"error": "rate"}))
    with pytest.raises(ProviderError) as ei:
        await make_provider().search("python", 3)
    assert ei.value.status == 429


@pytest.mark.asyncio
@respx.mock
async def test_extract_maps_contents_and_failures():
    respx.post(f"{EXA}/contents").mock(return_value=httpx.Response(200, json={
        "results": [{"url": "https://a.com", "title": "AT", "text": "x" * 500}],
        "failedResults": [{"url": "https://bad.com", "error": "not found"}],
    }))
    items = await make_provider().extract(["https://a.com", "https://bad.com"], max_chars=100)
    by_url = {i.url: i for i in items}
    assert by_url["https://a.com"].content == "x" * 100
    assert by_url["https://a.com"].raw_content == "x" * 500
    assert by_url["https://bad.com"].error == "not found"
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/pytest tests/providers/test_exa.py -v`
Expected: FAIL——`search` 抛 `NotImplementedError`

- [ ] **Step 3: 实现**

`src/searchhub/providers/exa.py`:
```python
from __future__ import annotations

from typing import Any

from searchhub.models import ExtractItem, SearchItem
from searchhub.providers.base import Provider, ProviderError


class ExaProvider(Provider):
    id = "exa"
    capabilities = frozenset({"search", "extract"})
    REQUIRES_KEY = True
    SEARCH_URL = "https://api.exa.ai/search"
    CONTENTS_URL = "https://api.exa.ai/contents"

    async def search(self, query: str, limit: int) -> list[SearchItem]:
        body = {"query": query, "num_results": limit, "type": "auto", "contents": {"text": True}}
        return await self._run(self.SEARCH_URL, body, self._map_search, limit=limit)

    async def extract(self, urls: list[str], *, fmt: str = "markdown",
                      max_chars: int = 15000) -> list[ExtractItem]:
        body = {"urls": urls, "text": True}
        return await self._run(self.CONTENTS_URL, body, self._map_extract, max_chars=max_chars)

    async def _run(self, url: str, body: dict, mapper, **kw):
        async with self._use_key() as key:
            headers = {"x-api-key": key}
            try:
                resp = await self.http.post(url, json=body, headers=headers)
            except Exception as e:
                self._report(key, None)
                raise ProviderError(self.id, f"http error: {e.__class__.__name__}")
            if resp.status_code >= 400:
                self._report(key, resp.status_code)
                raise ProviderError(self.id, f"exa http {resp.status_code}", status=resp.status_code)
        return mapper(resp.json(), **kw)

    async def _use_key(self):
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def ctx():
            if self.key_pool is None:
                yield None
                return
            async with self.key_pool.use() as key:
                yield key

        return ctx()

    def _report(self, key: str | None, status: int | None) -> None:
        if key is not None and self.key_pool is not None:
            self.key_pool.report_error(key, status)

    def _map_search(self, data: dict, limit: int) -> list[SearchItem]:
        items = []
        for i, r in enumerate(data.get("results", [])):
            items.append(SearchItem(
                title=r.get("title", ""),
                url=r.get("url", ""),
                description=self.truncate(r.get("text") or "", 300),
                position=i,
                provider=self.id,
                published_at=r.get("publishedDate"),
            ))
        return items

    def _map_extract(self, data: dict, max_chars: int) -> list[ExtractItem]:
        items = []
        for r in data.get("results", []):
            raw = r.get("text") or ""
            items.append(ExtractItem(
                url=r.get("url", ""),
                title=r.get("title", ""),
                content=self.truncate(raw, max_chars),
                raw_content=raw,
                provider=self.id,
            ))
        for f in data.get("failedResults", []):
            items.append(ExtractItem(url=f.get("url", ""), error=f.get("error", "extract failed"), provider=self.id))
        return items
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/pytest tests/providers/test_exa.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: 提交**

```bash
git add src/searchhub/providers/exa.py tests/providers/test_exa.py
git commit -m "feat: exa provider (search + extract)"
```

---

### Task 9: Adapter — tavily（search + extract）

**Files:**
- Modify: `src/searchhub/providers/tavily.py`（替换占位）
- Test: `tests/providers/test_tavily.py`

**Interfaces:**
- Consumes: 同 exa 模式（`_use_key`/`_report` 为 Provider 共享逻辑——本任务把这两个辅助方法**移到 base.py 的 Provider 类**，exa.py 同步删掉本地副本）
- Produces: `TavilyProvider.search(query, limit)` → `POST https://api.tavily.com/search`，header `Authorization: Bearer <key>`，body `{"query", "max_results": limit, "search_depth": "basic"}`；映射 `results[]` → `SearchItem(title, url, description=content)`
- Produces: `TavilyProvider.extract(urls, fmt="markdown", max_chars=15000)` → `POST https://api.tavily.com/extract`，body `{"urls", "format": fmt}`；映射 `results[]` → `ExtractItem(url, raw_content, content=truncate)`；`failed_results[]` → `ExtractItem(error=...)`

- [ ] **Step 1: 重构共享逻辑并更新 exa 测试（先跑通）**

在 `src/searchhub/providers/base.py` 的 Provider 类中追加：
```python
    def _use_key(self):
        @asynccontextmanager
        async def ctx():
            if self.key_pool is None:
                yield None
                return
            async with self.key_pool.use() as key:
                yield key

        return ctx()

    def _report(self, key: str | None, status: int | None) -> None:
        if key is not None and self.key_pool is not None:
            self.key_pool.report_error(key, status)
```
并删除 exa.py 中同名本地方法（保留 `_run` 之外逻辑不变）。import 加 `from contextlib import asynccontextmanager`。

Run: `.venv/bin/pytest tests/providers/test_exa.py -v`
Expected: PASS——重构不破坏 exa

- [ ] **Step 2: 写失败测试**

`tests/providers/test_tavily.py`:
```python
import httpx
import respx
import pytest

from searchhub.config import ProviderConfig
from searchhub.providers.base import ProviderError
from searchhub.providers.tavily import TavilyProvider

TAVILY = "https://api.tavily.com"


def make_provider():
    cfg = ProviderConfig(id="tavily", capabilities=["search", "extract"])
    return TavilyProvider(cfg, ["k1"], httpx.AsyncClient())


@pytest.mark.asyncio
@respx.mock
async def test_search_maps_results():
    respx.post(f"{TAVILY}/search").mock(return_value=httpx.Response(200, json={
        "results": [{"title": "T", "url": "https://a.com", "content": "desc"}]
    }))
    items = await make_provider().search("python", 3)
    assert items[0].description == "desc"
    assert items[0].provider == "tavily"
    sent = respx.calls[0].request
    assert sent.headers["authorization"] == "Bearer k1"


@pytest.mark.asyncio
@respx.mock
async def test_search_401_raises():
    respx.post(f"{TAVILY}/search").mock(return_value=httpx.Response(401, json={"error": "bad key"}))
    with pytest.raises(ProviderError) as ei:
        await make_provider().search("python", 3)
    assert ei.value.status == 401


@pytest.mark.asyncio
@respx.mock
async def test_extract_maps_results_and_failures():
    respx.post(f"{TAVILY}/extract").mock(return_value=httpx.Response(200, json={
        "results": [{"url": "https://a.com", "raw_content": "body"}],
        "failed_results": [{"url": "https://bad.com", "error": "failed to extract"}],
    }))
    items = await make_provider().extract(["https://a.com", "https://bad.com"])
    by_url = {i.url: i for i in items}
    assert by_url["https://a.com"].content == "body"
    assert by_url["https://bad.com"].error == "failed to extract"
```

- [ ] **Step 3: 运行确认失败**

Run: `.venv/bin/pytest tests/providers/test_tavily.py -v`
Expected: FAIL——`search` 抛 `NotImplementedError`

- [ ] **Step 4: 实现**

`src/searchhub/providers/tavily.py`:
```python
from __future__ import annotations

from searchhub.models import ExtractItem, SearchItem
from searchhub.providers.base import Provider, ProviderError


class TavilyProvider(Provider):
    id = "tavily"
    capabilities = frozenset({"search", "extract"})
    REQUIRES_KEY = True
    SEARCH_URL = "https://api.tavily.com/search"
    EXTRACT_URL = "https://api.tavily.com/extract"

    async def search(self, query: str, limit: int) -> list[SearchItem]:
        body = {"query": query, "max_results": limit, "search_depth": "basic"}
        async with self._use_key() as key:
            headers = {"Authorization": f"Bearer {key}"}
            try:
                resp = await self.http.post(self.SEARCH_URL, json=body, headers=headers)
            except Exception as e:
                self._report(key, None)
                raise ProviderError(self.id, f"http error: {e.__class__.__name__}")
            if resp.status_code >= 400:
                self._report(key, resp.status_code)
                raise ProviderError(self.id, f"tavily http {resp.status_code}", status=resp.status_code)
        return [
            SearchItem(title=r.get("title", ""), url=r.get("url", ""),
                       description=r.get("content", ""), position=i, provider=self.id)
            for i, r in enumerate(resp.json().get("results", []))
        ]

    async def extract(self, urls: list[str], *, fmt: str = "markdown",
                      max_chars: int = 15000) -> list[ExtractItem]:
        body = {"urls": urls, "format": fmt}
        async with self._use_key() as key:
            headers = {"Authorization": f"Bearer {key}"}
            try:
                resp = await self.http.post(self.EXTRACT_URL, json=body, headers=headers)
            except Exception as e:
                self._report(key, None)
                raise ProviderError(self.id, f"http error: {e.__class__.__name__}")
            if resp.status_code >= 400:
                self._report(key, resp.status_code)
                raise ProviderError(self.id, f"tavily http {resp.status_code}", status=resp.status_code)
        data = resp.json()
        items = []
        for r in data.get("results", []):
            raw = r.get("raw_content") or ""
            items.append(ExtractItem(url=r.get("url", ""), raw_content=raw,
                                     content=self.truncate(raw, max_chars), provider=self.id))
        for f in data.get("failed_results", []):
            items.append(ExtractItem(url=f.get("url", ""), error=f.get("error", "extract failed"), provider=self.id))
        return items
```

- [ ] **Step 5: 运行确认通过**

Run: `.venv/bin/pytest tests/providers/test_exa.py tests/providers/test_tavily.py -v`
Expected: PASS（6 passed）

- [ ] **Step 6: 提交**

```bash
git add src/searchhub/providers/base.py src/searchhub/providers/exa.py src/searchhub/providers/tavily.py tests/providers/test_tavily.py
git commit -m "feat: tavily provider (search + extract); share key-pool helpers in base"
```

---

### Task 10: Adapter — ddg（search，本地库）

**Files:**
- Modify: `src/searchhub/providers/ddg.py`（替换占位）
- Test: `tests/providers/test_ddg.py`

**Interfaces:**
- Consumes: `Provider`；ddgs 库 `from ddgs import DDGS`；`DDGS().text(query, max_results=limit)` → `[{title, href, body}]`
- Produces: `DdgProvider.search(query, limit)`：`asyncio.to_thread(self._search_sync, query, limit)`；无 key（REQUIRES_KEY=False）；返回 `SearchItem(title, url=href, description=body, position, provider="ddg")`

- [ ] **Step 1: 写失败测试**

`tests/providers/test_ddg.py`（monkeypatch 目标是 `ddgs.DDGS`——ddg.py 在 `_search_sync` 内 `from ddgs import DDGS`，调用时从该模块取）:
```python
import pytest

from searchhub.config import ProviderConfig
from searchhub.providers.ddg import DdgProvider


class FakeDDGS:
    def __init__(self, results):
        self.results = results

    def text(self, query, max_results=10, **kw):
        return self.results


def make_provider():
    cfg = ProviderConfig(id="ddg", capabilities=["search"])
    return DdgProvider(cfg, [], None)


@pytest.mark.asyncio
async def test_search_maps_href_and_body(monkeypatch):
    monkeypatch.setattr("ddgs.DDGS", lambda *a, **kw: FakeDDGS([
        {"title": "T1", "href": "https://a.com", "body": "desc1"},
        {"title": "T2", "href": "https://b.com", "body": "desc2"},
    ]))
    items = await make_provider().search("python", 3)
    assert [i.title for i in items] == ["T1", "T2"]
    assert items[0].url == "https://a.com"
    assert items[0].description == "desc1"
    assert items[0].position == 0
    assert items[1].position == 1


@pytest.mark.asyncio
async def test_search_empty_results(monkeypatch):
    monkeypatch.setattr("ddgs.DDGS", lambda *a, **kw: FakeDDGS([]))
    assert await make_provider().search("nothing", 3) == []


@pytest.mark.asyncio
async def test_search_is_offloaded_to_thread(monkeypatch):
    import threading
    seen = {}
    class TDDGS(FakeDDGS):
        def text(self, query, max_results=10, **kw):
            seen["thread"] = threading.current_thread().name
            return []
    monkeypatch.setattr("ddgs.DDGS", lambda *a, **kw: TDDGS([]))
    await make_provider().search("python", 3)
    assert seen["thread"] != threading.main_thread().name
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/pytest tests/providers/test_ddg.py -v`
Expected: FAIL

- [ ] **Step 3: 实现**

`src/searchhub/providers/ddg.py`:
```python
from __future__ import annotations

import asyncio

from searchhub.models import SearchItem
from searchhub.providers.base import Provider


class DdgProvider(Provider):
    id = "ddg"
    capabilities = frozenset({"search"})
    REQUIRES_KEY = False

    async def search(self, query: str, limit: int) -> list[SearchItem]:
        try:
            results = await asyncio.to_thread(self._search_sync, query, limit)
        except Exception as e:
            raise type(e)(f"ddg: {e}") from e
        return [
            SearchItem(title=r.get("title", ""), url=r.get("href", ""),
                       description=r.get("body", ""), position=i, provider=self.id)
            for i, r in enumerate(results)
        ]

    def _search_sync(self, query: str, limit: int) -> list[dict]:
        from ddgs import DDGS

        return DDGS().text(query, max_results=limit)
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/pytest tests/providers/test_ddg.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: 提交**

```bash
git add src/searchhub/providers/ddg.py tests/providers/test_ddg.py
git commit -m "feat: ddg provider (search, ddgs library)"
```

---

### Task 11: Adapter — searxng（search，HTTP）

**Files:**
- Modify: `src/searchhub/providers/searxng.py`（替换占位）
- Test: `tests/providers/test_searxng.py`

**Interfaces:**
- Produces: `SearxngProvider.search(query, limit)` → `GET {base_url}/search`，params `{"q": query, "format": "json", "safesearch": 1}`；`base_url` 取自 `cfg.base_url`（无则 `ProviderError`）；映射 `results[]` → `SearchItem(title, url, description=content, position)`；限流：`cfg.key_pool.rps_limit` 建 TokenBucket（无 key provider 用令牌桶防自爆）
- REQUIRES_KEY=False

- [ ] **Step 1: 写失败测试**

`tests/providers/test_searxng.py`:
```python
import httpx
import respx
import pytest

from searchhub.config import ProviderConfig
from searchhub.providers.base import ProviderError
from searchhub.providers.searxng import SearxngProvider


def make_provider(base_url="http://searxng:8080"):
    cfg = ProviderConfig(id="searxng", capabilities=["search"], base_url=base_url)
    return SearxngProvider(cfg, [], httpx.AsyncClient())


@pytest.mark.asyncio
@respx.mock
async def test_search_maps_results():
    respx.get("http://searxng:8080/search").mock(return_value=httpx.Response(200, json={
        "results": [{"title": "T", "url": "https://a.com", "content": "desc"}]
    }))
    items = await make_provider().search("python", 3)
    assert items[0].title == "T"
    assert items[0].url == "https://a.com"
    assert items[0].description == "desc"
    assert "format=json" in str(respx.calls[0].request.url)


@pytest.mark.asyncio
@respx.mock
async def test_search_500_raises():
    respx.get("http://searxng:8080/search").mock(return_value=httpx.Response(500))
    with pytest.raises(ProviderError):
        await make_provider().search("python", 3)


@pytest.mark.asyncio
async def test_search_without_base_url_raises():
    with pytest.raises(ProviderError):
        await make_provider(base_url=None).search("python", 3)
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/pytest tests/providers/test_searxng.py -v`
Expected: FAIL

- [ ] **Step 3: 实现**

`src/searchhub/providers/searxng.py`:
```python
from __future__ import annotations

from searchhub.engine.rate_limit import TokenBucket
from searchhub.models import SearchItem
from searchhub.providers.base import Provider, ProviderError


class SearxngProvider(Provider):
    id = "searxng"
    capabilities = frozenset({"search"})
    REQUIRES_KEY = False

    def __init__(self, cfg, keys, http):
        super().__init__(cfg, keys, http)
        self._bucket = TokenBucket(cfg.key_pool.rps_limit, capacity=max(1.0, cfg.key_pool.rps_limit))

    async def search(self, query: str, limit: int) -> list[SearchItem]:
        if not self.cfg.base_url:
            raise ProviderError(self.id, "searxng base_url not configured")
        await self._bucket.acquire()
        url = self.cfg.base_url.rstrip("/") + "/search"
        try:
            resp = await self.http.get(url, params={"q": query, "format": "json", "safesearch": 1})
        except Exception as e:
            raise ProviderError(self.id, f"http error: {e.__class__.__name__}")
        if resp.status_code >= 400:
            raise ProviderError(self.id, f"searxng http {resp.status_code}", status=resp.status_code)
        return [
            SearchItem(title=r.get("title", ""), url=r.get("url", ""),
                       description=r.get("content", ""), position=i, provider=self.id)
            for i, r in enumerate(resp.json().get("results", []))
        ]
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/pytest tests/providers/test_searxng.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: 提交**

```bash
git add src/searchhub/providers/searxng.py tests/providers/test_searxng.py
git commit -m "feat: searxng provider (search, JSON API)"
```

---

### Task 12: Adapter — jina + trafilatura（extract）

**Files:**
- Modify: `src/searchhub/providers/jina.py`（替换占位）
- Modify: `src/searchhub/providers/trafilatura_py.py`（替换占位）
- Test: `tests/providers/test_jina.py`
- Test: `tests/providers/test_trafilatura.py`

**Interfaces:**
- Produces: `JinaProvider.extract(urls, fmt="markdown", max_chars=15000)`：对每个 URL `GET https://r.jina.ai/{url}`，header `Authorization: Bearer <key>`（有 key 时）、`X-Return-Format: fmt`；响应为纯文本，title 取首行去 `# ` 前缀；`REQUIRES_KEY=False`（可选 key 存 secrets `JINA_KEY_1`）；每个 URL 失败 → `ExtractItem(error=...)`（单 URL 失败不炸整体）
- Produces: `TrafilaturaProvider.extract(urls, fmt="markdown", max_chars=15000)`：`asyncio.to_thread` 跑 `trafilatura.fetch_url(url)` + `trafilatura.extract(html, output_format=...)`（markdown→`"markdown"`，text→`"txt"`）；title 从 HTML `<title>` 正则提取；失败 → `ExtractItem(error=...)`；`REQUIRES_KEY=False`，受 `cfg.key_pool.rps_limit` 令牌桶限流
- 两个 provider 的 extract 都**不**抛 ProviderError（单 URL 语义），但 KeyPool 上报用于 jina 的 key 冷却

- [ ] **Step 1: 写失败测试**

`tests/providers/test_jina.py`:
```python
import httpx
import respx
import pytest

from searchhub.config import ProviderConfig
from searchhub.providers.jina import JinaProvider


def make_provider(keys=None):
    cfg = ProviderConfig(id="jina", capabilities=["extract"])
    return JinaProvider(cfg, keys or [], httpx.AsyncClient())


@pytest.mark.asyncio
@respx.mock
async def test_extract_plain_text():
    respx.get("https://r.jina.ai/https://a.com").mock(
        return_value=httpx.Response(200, text="# Page Title\n\nBody text here"))
    items = await make_provider().extract(["https://a.com"])
    assert items[0].title == "Page Title"
    assert items[0].content == "Body text here"
    assert items[0].provider == "jina"


@pytest.mark.asyncio
@respx.mock
async def test_extract_sends_key_when_available():
    respx.get("https://r.jina.ai/https://a.com").mock(return_value=httpx.Response(200, text="x"))
    await make_provider(["jk"]).extract(["https://a.com"])
    assert respx.calls[0].request.headers.get("authorization") == "Bearer jk"


@pytest.mark.asyncio
@respx.mock
async def test_extract_failure_is_per_url():
    respx.get("https://r.jina.ai/https://bad.com").mock(return_value=httpx.Response(500))
    items = await make_provider().extract(["https://bad.com"])
    assert items[0].error is not None
    assert items[0].url == "https://bad.com"
```

`tests/providers/test_trafilatura.py`（monkeypatch 目标是 `trafilatura.fetch_url`/`trafilatura.extract`——trafilatura_py.py 在 `_extract_sync` 内 `from trafilatura import ...`）:
```python
import pytest

from searchhub.config import ProviderConfig
from searchhub.providers.trafilatura_py import TrafilaturaProvider


def make_provider():
    cfg = ProviderConfig(id="trafilatura", capabilities=["extract"])
    return TrafilaturaProvider(cfg, [], None)


@pytest.mark.asyncio
async def test_extract_uses_fetch_and_extract(monkeypatch):
    calls = {}

    def fake_fetch(url):
        calls["url"] = url
        return "<html><head><title>TT</title></head><body><p>Hello</p></body></html>"

    def fake_extract(html, output_format="txt"):
        calls["fmt"] = output_format
        return "Hello"

    monkeypatch.setattr("trafilatura.fetch_url", fake_fetch)
    monkeypatch.setattr("trafilatura.extract", fake_extract)
    items = await make_provider().extract(["https://a.com"], fmt="text")
    assert items[0].title == "TT"
    assert items[0].content == "Hello"
    assert calls["fmt"] == "txt"


@pytest.mark.asyncio
async def test_extract_failure_is_per_url(monkeypatch):
    def fake_fetch(url):
        raise RuntimeError("network down")

    monkeypatch.setattr("trafilatura.fetch_url", fake_fetch)
    items = await make_provider().extract(["https://a.com"])
    assert items[0].error is not None


@pytest.mark.asyncio
async def test_extract_offloaded_to_thread(monkeypatch):
    import threading
    seen = {}

    def fake_fetch(url):
        seen["t"] = threading.current_thread().name
        return "<html><title>T</title></html>"

    monkeypatch.setattr("trafilatura.fetch_url", fake_fetch)
    await make_provider().extract(["https://a.com"])
    assert seen["t"] != threading.main_thread().name
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/pytest tests/providers/test_jina.py tests/providers/test_trafilatura.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 jina**

`src/searchhub/providers/jina.py`:
```python
from __future__ import annotations

import re

from searchhub.models import ExtractItem
from searchhub.providers.base import Provider, ProviderError

_TITLE_RE = re.compile(r"^#+\s*(.+?)\s*$")


class JinaProvider(Provider):
    id = "jina"
    capabilities = frozenset({"extract"})
    REQUIRES_KEY = False
    BASE = "https://r.jina.ai/"

    async def extract(self, urls: list[str], *, fmt: str = "markdown",
                      max_chars: int = 15000) -> list[ExtractItem]:
        items: list[ExtractItem] = []
        for url in urls:
            items.append(await self._extract_one(url, fmt, max_chars))
        return items

    async def _extract_one(self, url: str, fmt: str, max_chars: int) -> ExtractItem:
        headers = {"X-Return-Format": fmt}
        key = self.keys[0] if self.keys else None
        if key:
            headers["Authorization"] = f"Bearer {key}"
        try:
            async with self._use_key() as k:
                resp = await self.http.get(self.BASE + url, headers=headers)
            if resp.status_code >= 400:
                if k is not None:
                    self._report(k, resp.status_code)
                return ExtractItem(url=url, error=f"jina http {resp.status_code}", provider=self.id)
        except Exception as e:
            return ExtractItem(url=url, error=f"jina: {e.__class__.__name__}", provider=self.id)
        text = resp.text
        title = ""
        m = _TITLE_RE.match(text.strip())
        if m:
            title = m.group(1)
            text = text[m.end():].lstrip()
        return ExtractItem(url=url, title=title, content=self.truncate(text, max_chars),
                           raw_content=text, provider=self.id)
```

- [ ] **Step 4: 实现 trafilatura**

`src/searchhub/providers/trafilatura_py.py`:
```python
from __future__ import annotations

import asyncio
import re

from searchhub.engine.rate_limit import TokenBucket
from searchhub.models import ExtractItem
from searchhub.providers.base import Provider

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)


class TrafilaturaProvider(Provider):
    id = "trafilatura"
    capabilities = frozenset({"extract"})
    REQUIRES_KEY = False

    def __init__(self, cfg, keys, http):
        super().__init__(cfg, keys, http)
        self._bucket = TokenBucket(cfg.key_pool.rps_limit, capacity=max(1.0, cfg.key_pool.rps_limit))

    async def extract(self, urls: list[str], *, fmt: str = "markdown",
                      max_chars: int = 15000) -> list[ExtractItem]:
        return await asyncio.gather(*(self._extract_one(u, fmt, max_chars) for u in urls))

    async def _extract_one(self, url: str, fmt: str, max_chars: int) -> ExtractItem:
        await self._bucket.acquire()
        try:
            result = await asyncio.to_thread(self._extract_sync, url, fmt)
        except Exception as e:
            return ExtractItem(url=url, error=f"trafilatura: {e.__class__.__name__}", provider=self.id)
        if result is None:
            return ExtractItem(url=url, error="trafilatura: no content extracted", provider=self.id)
        html, text = result
        m = _TITLE_RE.search(html or "")
        title = m.group(1).strip() if m else ""
        return ExtractItem(url=url, title=title, content=self.truncate(text, max_chars),
                           raw_content=text, provider=self.id)

    def _extract_sync(self, url: str, fmt: str) -> tuple[str | None, str | None]:
        from trafilatura import extract, fetch_url

        html = fetch_url(url)
        text = extract(html, output_format="markdown" if fmt == "markdown" else "txt")
        return html, text
```

- [ ] **Step 5: 运行确认通过**

Run: `.venv/bin/pytest tests/providers/test_jina.py tests/providers/test_trafilatura.py -v`
Expected: PASS（6 passed）

- [ ] **Step 6: 提交**

```bash
git add src/searchhub/providers/jina.py src/searchhub/providers/trafilatura_py.py tests/providers/test_jina.py tests/providers/test_trafilatura.py
git commit -m "feat: jina + trafilatura extract providers"
```

---

### Task 13: SQLite 存储与缓存（db + CacheRepo）

**Files:**
- Create: `src/searchhub/storage/__init__.py`
- Create: `src/searchhub/storage/db.py`
- Create: `src/searchhub/storage/cache.py`
- Test: `tests/storage/test_cache.py`

**Interfaces:**
- Produces: `db.open_db(path: Path) -> aiosqlite.Connection`（`PRAGMA journal_mode=WAL`，`PRAGMA foreign_keys=ON`）
- Produces: `db.init_schema(conn)`——`schema_version` 表 + 表 `cache`：`(cache_key TEXT PRIMARY KEY, payload TEXT, created_at REAL, expires_at REAL)`
- Produces: `class CacheRepo`: `__init__(self, db_path: Path)`；`async def get(self, key: str) -> str | None`（过期即删除返回 None）；`async def put(self, key: str, payload: str, ttl_s: int) -> None`；`async def purge_expired(self) -> int`；`async def close(self)`
- Produces: `engine/cache_keys.py` 小工具：`search_cache_key(query: str, limit: int, providers: str, strategy: str) -> str`、`extract_cache_key(url: str, fmt: str, max_chars: int) -> str`（均为 sha1 hex）

- [ ] **Step 1: 写失败测试**

`tests/storage/test_cache.py`:
```python
import time
from pathlib import Path

import pytest

from searchhub.engine.cache_keys import extract_cache_key, search_cache_key
from searchhub.storage.cache import CacheRepo


@pytest.fixture
async def repo(data_dir: Path):
    r = CacheRepo(data_dir / "cache.db")
    yield r
    await r.close()


@pytest.mark.asyncio
async def test_put_get_roundtrip(repo):
    await repo.put("k1", "v1", ttl_s=600)
    assert await repo.get("k1") == "v1"


@pytest.mark.asyncio
async def test_expired_entry_purged(repo):
    await repo.put("k1", "v1", ttl_s=1)
    time.sleep(1.1)
    assert await repo.purge_expired() == 1
    assert await repo.get("k1") is None


@pytest.mark.asyncio
async def test_overwrite_extends(repo):
    await repo.put("k1", "v1", ttl_s=60)
    await repo.put("k1", "v2", ttl_s=60)
    assert await repo.get("k1") == "v2"


@pytest.mark.asyncio
async def test_cache_keys_stable_and_distinct():
    assert search_cache_key("q", 5, "all", "fanout") == search_cache_key("q", 5, "all", "fanout")
    assert search_cache_key("q", 5, "all", "fanout") != search_cache_key("q", 5, "all", "rotation")
    assert extract_cache_key("https://a.com", "markdown", 1000) != extract_cache_key("https://a.com", "text", 1000)
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/pytest tests/storage/test_cache.py -v`
Expected: FAIL

- [ ] **Step 3: 实现**

`src/searchhub/storage/db.py`:
```python
from __future__ import annotations

from pathlib import Path

import aiosqlite


async def open_db(path: Path) -> aiosqlite.Connection:
    conn = await aiosqlite.connect(path)
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute("PRAGMA foreign_keys=ON")
    await conn.execute("PRAGMA busy_timeout=5000")
    return conn


_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);
INSERT OR IGNORE INTO schema_version (version) VALUES (1);

CREATE TABLE IF NOT EXISTS cache (
    cache_key TEXT PRIMARY KEY,
    payload TEXT NOT NULL,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cache_expires ON cache (expires_at);
"""


async def init_schema(conn: aiosqlite.Connection) -> None:
    await conn.executescript(_SCHEMA)
    await conn.commit()
```

`src/searchhub/storage/cache.py`:
```python
from __future__ import annotations

import json
import time
from pathlib import Path

from searchhub.storage.db import init_schema, open_db


class CacheRepo:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self._conn = None

    async def _conn_ensure(self):
        if self._conn is None:
            self._conn = await open_db(self.db_path)
            await init_schema(self._conn)
        return self._conn

    async def get(self, key: str) -> str | None:
        conn = await self._conn_ensure()
        cur = await conn.execute(
            "SELECT payload, expires_at FROM cache WHERE cache_key = ?", (key,))
        row = await cur.fetchone()
        if row is None:
            return None
        payload, expires = row
        if expires < time.time():
            await conn.execute("DELETE FROM cache WHERE cache_key = ?", (key,))
            await conn.commit()
            return None
        return payload

    async def put(self, key: str, payload: str, ttl_s: int) -> None:
        conn = await self._conn_ensure()
        now = time.time()
        await conn.execute(
            "INSERT OR REPLACE INTO cache (cache_key, payload, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (key, payload, now, now + ttl_s),
        )
        await conn.commit()

    async def purge_expired(self) -> int:
        conn = await self._conn_ensure()
        cur = await conn.execute("DELETE FROM cache WHERE expires_at < ?", (time.time(),))
        await conn.commit()
        return cur.rowcount or 0

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
```

`src/searchhub/engine/cache_keys.py`:
```python
from __future__ import annotations

import hashlib


def _h(s: str) -> str:
    return hashlib.sha1(s.encode()).hexdigest()


def search_cache_key(query: str, limit: int, providers: str, strategy: str) -> str:
    return _h(f"search:{query}:{limit}:{providers}:{strategy}")


def extract_cache_key(url: str, fmt: str, max_chars: int) -> str:
    return _h(f"extract:{url}:{fmt}:{max_chars}")
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/pytest tests/storage/test_cache.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: 提交**

```bash
git add src/searchhub/storage src/searchhub/engine/cache_keys.py tests/storage/test_cache.py
git commit -m "feat: sqlite cache storage with TTL"
```

---

### Task 14: Orchestrator（search/extract 入口）

**Files:**
- Create: `src/searchhub/orchestrator.py`
- Test: `tests/test_orchestrator.py`

**Interfaces:**
- Consumes: ConfigService、CacheRepo、`build_registry`、`registry_for_capability`、`fanout`/`rotation`/`primary_fallback`、`merge_search`/`merge_extract`、`search_cache_key`/`extract_cache_key`
- Produces:
  - `class SearchHubEngine`: `__init__(self, config: ConfigService, cache: CacheRepo | None, http: httpx.AsyncClient)`
  - `def maybe_reload(self) -> bool`（调 config.maybe_reload，重建 registry）
  - `async def search(self, query: str, limit: int = 5, providers: str | None = None, strategy: str | None = None, cache: bool = True, timeout: float | None = None) -> SearchResponse`——语义：
    1. maybe_reload；registry 按 capability=search 过滤（providers 参数逗号分隔过滤 id，缺省全启用）
    2. 空 providers → `SearchResponse(success=False, error="no search provider enabled")`（data 用空 SearchData）
    3. cache 开启时先查缓存，命中 → meta.cached=True，跳过引擎
    4. strategy 默认取 cfg.strategy.default_mode；fanout → `fanout(calls, timeout)`；rotation/primary_fallback → `rotation`/`primary_fallback(list, "search", timeout, call)`
    5. merge_search(outcomes, limit, registry) 截断；写缓存（payload=json.dumps(items)）；meta 填 provider_stats、took_ms
  - `async def extract(self, urls: list[str], fmt: str = "markdown", max_chars: int = 15000, strategy: str | None = None, cache: bool = True, timeout: float | None = None) -> ExtractResponse`——语义同上，按 capability=extract；合并用 merge_extract(outcomes, urls, registry)；缓存按 URL 逐条存取
  - `def provider_status(self) -> list[dict]`（供 /v1/providers：id/capabilities/enabled/weight/priority/keys 状态）
- 内部统计：`self.stats: dict[str, dict]`（每 provider：calls/errors/sum_ms），search/extract 后更新

- [ ] **Step 1: 写失败测试**

`tests/test_orchestrator.py`（用假 provider 直插引擎注册表；注意注入后必须同步 `_version`，否则 maybe_reload 会用真实配置重建注册表）:
```python
import asyncio
import time
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from searchhub.config import ConfigService, ProviderConfig
from searchhub.models import SearchItem
from searchhub.orchestrator import SearchHubEngine
from searchhub.providers import build_registry


class FakeProvider:
    id = "fake"
    capabilities = frozenset({"search", "extract"})

    def __init__(self, pid, weight=10, fail=False, slow=0.0):
        self.id = pid
        self.cfg = SimpleNamespace(id=pid, capabilities=["search", "extract"],
                                   weight=weight, priority=100, max_results=8)
        self.fail = fail
        self.slow = slow
        self.calls = 0

    def supports(self, cap):
        return cap in self.capabilities

    async def search(self, query, limit):
        self.calls += 1
        if self.fail:
            from searchhub.providers.base import ProviderError
            raise ProviderError(self.id, "boom")
        if self.slow:
            await asyncio.sleep(self.slow)
        return [SearchItem(title=f"{query}-{self.id}", url=f"https://{self.id}.com",
                           position=0, provider=self.id)]

    async def extract(self, urls, **kw):
        from searchhub.models import ExtractItem
        return [ExtractItem(url=u, content=f"{self.id}:{u}", provider=self.id) for u in urls]


def make_engine(data_dir: Path, providers, strategy="fanout"):
    cs = ConfigService(data_dir)
    cs.load()
    cfg = cs.get()
    cfg.providers = [ProviderConfig(id=p["id"], capabilities=["search", "extract"])
                     for p in providers]
    cfg.strategy.default_mode = strategy
    cs.save_config(cfg)
    from searchhub.storage.cache import CacheRepo
    eng = SearchHubEngine(cs, CacheRepo(data_dir / "cache.db"), httpx.AsyncClient())
    eng._registry = {p["id"]: p["obj"] for p in providers}
    eng._version = cs.config_version
    return eng


@pytest.mark.asyncio
async def test_search_fanout_merges(data_dir):
    eng = make_engine(data_dir, [
        {"id": "a", "obj": FakeProvider("a", weight=5)},
        {"id": "b", "obj": FakeProvider("b", weight=10)},
    ])
    resp = await eng.search("python")
    assert resp.success
    assert len(resp.data.web) == 2
    assert resp.data.web[0].provider == "b"
    assert resp.meta["cached"] is False


@pytest.mark.asyncio
async def test_search_fanout_tolerates_failure(data_dir):
    eng = make_engine(data_dir, [
        {"id": "a", "obj": FakeProvider("a", fail=True)},
        {"id": "b", "obj": FakeProvider("b")},
    ])
    resp = await eng.search("python")
    assert resp.success
    assert [i.provider for i in resp.data.web] == ["b"]


@pytest.mark.asyncio
async def test_search_all_fail_returns_error(data_dir):
    eng = make_engine(data_dir, [{"id": "a", "obj": FakeProvider("a", fail=True)}])
    resp = await eng.search("python")
    assert resp.success is False
    assert "a" in resp.error


@pytest.mark.asyncio
async def test_search_caches_and_hits(data_dir):
    eng = make_engine(data_dir, [{"id": "a", "obj": FakeProvider("a")}])
    r1 = await eng.search("python")
    r2 = await eng.search("python")
    assert r1.meta["cached"] is False
    assert r2.meta["cached"] is True
    assert len(r2.data.web) == 1


@pytest.mark.asyncio
async def test_search_providers_filter(data_dir):
    eng = make_engine(data_dir, [
        {"id": "a", "obj": FakeProvider("a")},
        {"id": "b", "obj": FakeProvider("b")},
    ])
    resp = await eng.search("python", providers="b")
    assert [i.provider for i in resp.data.web] == ["b"]


@pytest.mark.asyncio
async def test_extract_merges_and_caches(data_dir):
    eng = make_engine(data_dir, [{"id": "a", "obj": FakeProvider("a")}])
    r1 = await eng.extract(["https://x.com"])
    r2 = await eng.extract(["https://x.com"])
    assert r1.success and r1.data[0].content == "a:https://x.com"
    assert r2.meta["cached"] is True


@pytest.mark.asyncio
async def test_extract_rotation_mode(data_dir):
    eng = make_engine(data_dir, [
        {"id": "a", "obj": FakeProvider("a")},
        {"id": "b", "obj": FakeProvider("b")},
    ], strategy="rotation")
    resp = await eng.extract(["https://x.com"])
    assert resp.success and resp.data[0].content.endswith("https://x.com")
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/pytest tests/test_orchestrator.py -v`
Expected: FAIL——模块不存在

- [ ] **Step 3: 实现**

`src/searchhub/orchestrator.py`:
```python
from __future__ import annotations

import json
import time
from typing import Any

import httpx

from searchhub.config import ConfigService
from searchhub.engine.cache_keys import extract_cache_key, search_cache_key
from searchhub.engine.merge import merge_extract, merge_search
from searchhub.engine.strategies import Outcome, fanout, primary_fallback, rotation
from searchhub.models import ExtractItem, SearchResponse, SearchData, SearchItem
from searchhub.providers import build_registry, registry_for_capability
from searchhub.providers.base import Provider
from searchhub.storage.cache import CacheRepo


class SearchHubEngine:
    def __init__(self, config: ConfigService, cache: CacheRepo | None, http: httpx.AsyncClient):
        self.config = config
        self.cache = cache
        self.http = http
        self._registry: dict[str, Provider] = {}
        self._version = -1
        self.stats: dict[str, dict[str, Any]] = {}

    def maybe_reload(self) -> bool:
        if self.config.maybe_reload() or self._version != self.config.config_version:
            self._registry = build_registry(self.config.get(), self.config.secrets(), self.http)
            self._version = self.config.config_version
            return True
        return False

    def _registry_for(self, cap: str) -> list[Provider]:
        self.maybe_reload()
        return registry_for_capability(self._registry, cap)

    def _filter(self, providers: list[Provider], only: str | None) -> list[Provider]:
        if not only:
            return providers
        wanted = {p.strip() for p in only.split(",") if p.strip()}
        return [p for p in providers if p.id in wanted]

    def _record(self, provider_id: str, ok: bool, took_ms: float) -> None:
        s = self.stats.setdefault(provider_id, {"calls": 0, "errors": 0, "sum_ms": 0.0})
        s["calls"] += 1
        s["sum_ms"] += took_ms
        if not ok:
            s["errors"] += 1

    async def search(self, query: str, limit: int = 5, providers: str | None = None,
                     strategy: str | None = None, cache: bool = True,
                     timeout: float | None = None) -> SearchResponse:
        start = time.monotonic()
        cfg = self.config.get()
        providers_list = self._filter(self._registry_for("search"), providers)
        if not providers_list:
            return SearchResponse(success=False, data=SearchData(web=[]),
                                  error=f"no search provider enabled",
                                  meta={"took_ms": 0})
        mode = strategy or cfg.strategy.default_mode
        t = timeout or cfg.strategy.timeout_s
        cache_key = search_cache_key(query, limit, providers or "all", mode)
        outcomes: list[Outcome] = []
        if self.cache and cache:
            hit = await self.cache.get(cache_key)
            if hit is not None:
                items = [SearchItem(**d) for d in json.loads(hit)]
                return SearchResponse(success=True, data=SearchData(web=items),
                                      meta={"took_ms": 0, "cached": True})
        if mode == "fanout":
            calls = [(p, p.search(query, min(limit, p.cfg.max_results))) for p in providers_list]
            outcomes = await fanout(calls, t)
        else:
            def call(p: Provider):
                return p.search(query, min(limit, p.cfg.max_results))

            if mode == "rotation":
                outcomes = [await rotation(providers_list, "search", t, call)]
            else:
                outcomes = [await primary_fallback(providers_list, "search", t, call)]
        for o in outcomes:
            self._record(o.provider_id, o.error is None, o.took_ms)
        if not any(o.items for o in outcomes if not o.error):
            details = "; ".join(f"{o.provider_id}: {o.error}" for o in outcomes)
            return SearchResponse(success=False, data=SearchData(web=[]), error=details,
                                  meta={"took_ms": (time.monotonic() - start) * 1000})
        merged = merge_search(outcomes, limit, self._registry)
        if self.cache and cache:
            await self.cache.put(cache_key, json.dumps([i.model_dump() for i in merged]),
                                 cfg.cache.search_ttl_s)
        return SearchResponse(success=True, data=SearchData(web=merged),
                              meta={"took_ms": (time.monotonic() - start) * 1000,
                                    "cached": False,
                                    "provider_stats": {
                                        o.provider_id: {"success": o.error is None,
                                                        "took_ms": round(o.took_ms, 1),
                                                        "count": len(o.items) if o.items else 0,
                                                        "error": o.error}
                                        for o in outcomes}})

    async def extract(self, urls: list[str], fmt: str = "markdown", max_chars: int = 15000,
                      strategy: str | None = None, cache: bool = True,
                      timeout: float | None = None) -> ExtractResponse:
        start = time.monotonic()
        cfg = self.config.get()
        providers_list = self._filter(self._registry_for("extract"), None)
        if not providers_list:
            return ExtractResponse(success=False,
                                   data=[ExtractItem(url=u, error="no extract provider enabled") for u in urls],
                                   meta={"took_ms": 0})
        mode = strategy or cfg.strategy.default_mode
        t = timeout or cfg.strategy.timeout_s
        final_items: list[ExtractItem] = []
        cached_any = False
        remaining: list[str] = []
        if self.cache and cache:
            for url in urls:
                hit = await self.cache.get(extract_cache_key(url, fmt, max_chars))
                if hit is not None:
                    final_items.append(ExtractItem(**json.loads(hit)))
                    cached_any = True
                else:
                    remaining.append(url)
        else:
            remaining = urls
        if remaining:
            if mode == "fanout":
                calls = [(p, p.extract(remaining, fmt=fmt, max_chars=max_chars)) for p in providers_list]
                outcomes = await fanout(calls, t)
            else:
                def call(p: Provider):
                    return p.extract(remaining, fmt=fmt, max_chars=max_chars)

                if mode == "rotation":
                    outcomes = [await rotation(providers_list, "extract", t, call)]
                else:
                    outcomes = [await primary_fallback(providers_list, "extract", t, call)]
            for o in outcomes:
                self._record(o.provider_id, o.error is None, o.took_ms)
            merged = merge_extract(outcomes, remaining, self._registry)
            if self.cache and cache:
                for item in merged:
                    if item.error is None:
                        await self.cache.put(extract_cache_key(item.url, fmt, max_chars),
                                             json.dumps(item.model_dump()), cfg.cache.extract_ttl_s)
            final_items.extend(merged)
        return ExtractResponse(success=True, data=final_items,
                               meta={"took_ms": (time.monotonic() - start) * 1000,
                                     "cached": cached_any})

    def provider_status(self) -> list[dict]:
        self.maybe_reload()
        result = []
        for pid, p in sorted(self._registry.items()):
            entry = {
                "id": pid,
                "capabilities": sorted(p.capabilities),
                "weight": p.cfg.weight,
                "priority": p.cfg.priority,
                "keys": [],
            }
            if p.key_pool is not None:
                entry["keys"] = p.key_pool.status()
            s = self.stats.get(pid)
            if s:
                entry["stats"] = {"calls": s["calls"], "errors": s["errors"],
                                  "avg_ms": round(s["sum_ms"] / max(1, s["calls"]), 1)}
            result.append(entry)
        return result
```

> 注：测试里 `eng._registry = {...}` 直接注入假 provider；`provider_status` 依赖 `_registry` 的键与 `p.cfg`，FakeProvider 用 `__new__` 构造时 cfg 在 `__init__` 设置，测试的 FakeProvider 构造已带 cfg 属性。

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/pytest tests/test_orchestrator.py -v`
Expected: PASS（8 passed）

- [ ] **Step 5: 提交**

```bash
git add src/searchhub/orchestrator.py tests/test_orchestrator.py
git commit -m "feat: orchestrator with strategy dispatch, cache, stats"
```

---

### Task 15: REST API（鉴权 + search/extract/providers 路由）

**Files:**
- Create: `src/searchhub/api/auth.py`
- Create: `src/searchhub/api/routes_search.py`
- Create: `src/searchhub/api/routes_extract.py`
- Create: `src/searchhub/api/routes_providers.py`
- Modify: `src/searchhub/api/app.py`（lifespan 初始化 engine/cache，挂路由，加异常处理返回统一错误形状）
- Test: `tests/api/test_auth.py`
- Test: `tests/api/test_search.py`
- Test: `tests/api/test_extract.py`
- Test: `tests/api/test_providers.py`

**Interfaces:**
- Produces: `searchhub.api.auth.require_token`（FastAPI dependency）：读 `Authorization: Bearer <token>`，sha256 与 `config.auth.tokens[].token_hash` 常量时间比较；失败 → 401 `{"success": false, "error": "invalid token"}`
- Produces: `/v1/search`（GET query 参数 + POST JSON body 均支持）：参数 `q`(必填)、`limit`(默认5)、`providers`、`strategy`、`cache`(默认true)、`timeout`；错误 → HTTP 400/401/500 但 body 统一 `{"success": false, "error": ...}`
- Produces: `/v1/extract`（GET: `urls` 逗号分隔；POST: `{"urls": [...]}`）：`format`(text|markdown)、`include_raw`(默认true，false 时 raw_content 置空)、`max_chars`(默认15000)、`cache`、`strategy`
- Produces: `/v1/providers`（GET，返回 engine.provider_status()）
- Auth 模型：`AppConfig.auth: AuthConfig`，`AuthConfig.tokens: list[TokenEntry]`，`TokenEntry: {name: str, token_hash: str}`（M2 管理 UI 才做增删，M1 手写 config.yaml 添加）

- [ ] **Step 1: 写失败测试**

`tests/api/test_auth.py`:
```python
import hashlib

import pytest
from fastapi.testclient import TestClient

from searchhub.api.app import create_app
from searchhub.config import AuthConfig, ConfigService, TokenEntry


@pytest.fixture
def app_with_token(data_dir):
    cs = ConfigService(data_dir)
    cs.load()
    cfg = cs.get()
    cfg.auth = AuthConfig(tokens=[TokenEntry(name="test", token_hash=hashlib.sha256(b"sekrit").hexdigest())])
    cs.save_config(cfg)
    return create_app(data_dir)


def test_healthz_needs_no_token(app):
    with TestClient(app) as c:
        assert c.get("/healthz").status_code == 200


def test_providers_requires_token(app_with_token):
    with TestClient(app_with_token) as c:
        assert c.get("/v1/providers").status_code == 401
        assert c.get("/v1/providers", headers={"Authorization": "Bearer wrong"}).status_code == 401
        r = c.get("/v1/providers", headers={"Authorization": "Bearer sekrit"})
        assert r.status_code == 200


def test_search_requires_token(app_with_token):
    with TestClient(app_with_token) as c:
        assert c.post("/v1/search", json={"q": "x"}).status_code == 401
```

`tests/api/test_search.py`:
```python
import hashlib

import pytest
from fastapi.testclient import TestClient

from searchhub.api.app import create_app
from searchhub.config import AuthConfig, ConfigService, ProviderConfig, TokenEntry


@pytest.fixture
def client(data_dir):
    cs = ConfigService(data_dir)
    cs.load()
    cfg = cs.get()
    cfg.auth = AuthConfig(tokens=[TokenEntry(name="t", token_hash=hashlib.sha256(b"tok").hexdigest())])
    cfg.providers = [ProviderConfig(id="ddg", capabilities=["search"])]
    cs.save_config(cfg)
    app = create_app(data_dir)
    # 注入假 ddg 适配器：monkeypatch PROVIDER_CLASSES 之后重建
    with TestClient(app) as c:
        yield c


AUTH = {"Authorization": "Bearer tok"}


def test_search_get_shape(client):
    from searchhub.models import SearchItem
    from searchhub.providers.ddg import DdgProvider

    original = DdgProvider.search

    async def fake_search(self, query, limit):
        return [SearchItem(title="T", url="https://x.com", description="D", position=0, provider="ddg")]

    DdgProvider.search = fake_search
    try:
        r = client.get("/v1/search", params={"q": "python"}, headers=AUTH)
    finally:
        DdgProvider.search = original
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"]["web"][0]["title"] == "T"
    assert body["data"]["web"][0]["url"] == "https://x.com"
    assert body["data"]["web"][0]["position"] == 0
    assert "meta" in body


def test_search_missing_q(client):
    r = client.get("/v1/search", headers=AUTH)
    assert r.status_code == 400
    assert r.json()["success"] is False


def test_search_no_provider_returns_error(data_dir):
    cs = ConfigService(data_dir)
    cs.load()
    cs.get().auth = AuthConfig(tokens=[TokenEntry(name="t", token_hash=hashlib.sha256(b"tok").hexdigest())])
    cs.save_config(cs.get())
    with TestClient(create_app(data_dir)) as c:
        r = c.get("/v1/search", params={"q": "x"}, headers=AUTH)
        assert r.status_code == 200
        assert r.json()["success"] is False
```

`tests/api/test_extract.py`:
```python
import hashlib

import pytest
from fastapi.testclient import TestClient

from searchhub.api.app import create_app
from searchhub.config import AuthConfig, ConfigService, ProviderConfig, TokenEntry


@pytest.fixture
def client(data_dir):
    cs = ConfigService(data_dir)
    cs.load()
    cfg = cs.get()
    cfg.auth = AuthConfig(tokens=[TokenEntry(name="t", token_hash=hashlib.sha256(b"tok").hexdigest())])
    cfg.providers = [ProviderConfig(id="trafilatura", capabilities=["extract"])]
    cs.save_config(cfg)
    app = create_app(data_dir)
    with TestClient(app) as c:
        yield c


AUTH = {"Authorization": "Bearer tok"}


def test_extract_get_and_post(client):
    from searchhub.models import ExtractItem
    from searchhub.providers.trafilatura_py import TrafilaturaProvider

    original = TrafilaturaProvider.extract

    async def fake_extract(self, urls, fmt="markdown", max_chars=15000):
        return [ExtractItem(url=u, title="TT", content=f"c-{u}", provider="trafilatura") for u in urls]

    TrafilaturaProvider.extract = fake_extract
    try:
        r = client.get("/v1/extract", params={"urls": "https://a.com,https://b.com"}, headers=AUTH)
        post = client.post("/v1/extract", json={"urls": ["https://a.com"]}, headers=AUTH)
    finally:
        TrafilaturaProvider.extract = original
    assert r.status_code == 200
    assert [i["url"] for i in r.json()["data"]] == ["https://a.com", "https://b.com"]
    assert post.json()["data"][0]["title"] == "TT"


def test_extract_include_raw_false(client):
    from searchhub.models import ExtractItem
    from searchhub.providers.trafilatura_py import TrafilaturaProvider

    original = TrafilaturaProvider.extract

    async def fake_extract(self, urls, fmt="markdown", max_chars=15000):
        return [ExtractItem(url=u, content="c", raw_content="RAW", provider="trafilatura") for u in urls]

    TrafilaturaProvider.extract = fake_extract
    try:
        r = client.get("/v1/extract", params={"urls": "https://a.com", "include_raw": "false"}, headers=AUTH)
    finally:
        TrafilaturaProvider.extract = original
    assert r.json()["data"][0]["raw_content"] == ""


def test_extract_invalid_format(client):
    r = client.get("/v1/extract", params={"urls": "https://a.com", "format": "pdf"}, headers=AUTH)
    assert r.status_code == 400
```

`tests/api/test_providers.py`:
```python
import hashlib

import pytest
from fastapi.testclient import TestClient

from searchhub.api.app import create_app
from searchhub.config import AuthConfig, ConfigService, ProviderConfig, TokenEntry


def test_providers_lists_capabilities(data_dir):
    cs = ConfigService(data_dir)
    cs.load()
    cfg = cs.get()
    cfg.auth = AuthConfig(tokens=[TokenEntry(name="t", token_hash=hashlib.sha256(b"tok").hexdigest())])
    cfg.providers = [
        ProviderConfig(id="ddg", capabilities=["search"]),
        ProviderConfig(id="trafilatura", capabilities=["extract"]),
    ]
    cs.save_config(cfg)
    with TestClient(create_app(data_dir)) as c:
        r = c.get("/v1/providers", headers={"Authorization": "Bearer tok"})
    assert r.status_code == 200
    caps = {p["id"]: p["capabilities"] for p in r.json()}
    assert caps["ddg"] == ["search"]
    assert caps["trafilatura"] == ["extract"]
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/pytest tests/api/ -v`
Expected: FAIL（路由不存在）

- [ ] **Step 3: 实现 auth 与路由**

`src/searchhub/api/auth.py`:
```python
from __future__ import annotations

import hashlib
import hmac

from fastapi import Depends, HTTPException, Request

from searchhub.config import AppConfig


def _authorized(config: AppConfig, token: str) -> bool:
    digest = hashlib.sha256(token.encode()).hexdigest()
    return any(hmac.compare_digest(digest, t.token_hash) for t in config.auth.tokens)


async def require_token(request: Request) -> None:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="invalid token")
    token = header[len("Bearer "):].strip()
    if not _authorized(request.app.state.engine.config.get(), token):
        raise HTTPException(status_code=401, detail="invalid token")
```

`src/searchhub/api/routes_search.py`:
```python
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from searchhub.api.auth import require_token

router = APIRouter(prefix="/v1/search", tags=["search"], dependencies=[Depends(require_token)])


class SearchBody(BaseModel):
    q: str = ""
    limit: int = Field(default=5, ge=1, le=50)
    providers: str | None = None
    strategy: str | None = None
    cache: bool = True
    timeout: float | None = None


@router.get("")
async def search_get(request: Request, q: str = "", limit: int = 5, providers: str | None = None,
                     strategy: str | None = None, cache: bool = True,
                     timeout: float | None = None):
    if not q:
        raise HTTPException(status_code=400, detail="q is required")
    try:
        return await request.app.state.engine.search(
            q, limit=limit, providers=providers, strategy=strategy, cache=cache, timeout=timeout)
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("")
async def search_post(request: Request, body: SearchBody):
    if not body.q:
        raise HTTPException(status_code=400, detail="q is required")
    try:
        return await request.app.state.engine.search(
            body.q, limit=body.limit, providers=body.providers, strategy=body.strategy,
            cache=body.cache, timeout=body.timeout)
    except Exception as e:
        return {"success": False, "error": str(e)}
```

`src/searchhub/api/routes_extract.py`:
```python
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from searchhub.api.auth import require_token

router = APIRouter(prefix="/v1/extract", tags=["extract"], dependencies=[Depends(require_token)])

VALID_FORMATS = {"text", "markdown"}


class ExtractBody(BaseModel):
    urls: list[str] = Field(min_length=1, max_length=20)
    format: str = "markdown"
    include_raw: bool = True
    max_chars: int = Field(default=15000, ge=100, le=1000000)
    cache: bool = True
    strategy: str | None = None
    timeout: float | None = None


async def _run(request: Request, urls: list[str], fmt: str, include_raw: bool, max_chars: int,
               cache: bool, strategy: str | None, timeout: float | None):
    if fmt not in VALID_FORMATS:
        raise HTTPException(status_code=400, detail="format must be text or markdown")
    resp = await request.app.state.engine.extract(
        urls, fmt=fmt, max_chars=max_chars, strategy=strategy, cache=cache, timeout=timeout)
    if not include_raw:
        for item in resp.data:
            item.raw_content = ""
    return resp


@router.get("")
async def extract_get(request: Request, urls: str, format: str = "markdown",
                      include_raw: bool = True, max_chars: int = 15000,
                      cache: bool = True, strategy: str | None = None,
                      timeout: float | None = None):
    url_list = [u.strip() for u in urls.split(",") if u.strip()]
    if not url_list:
        raise HTTPException(status_code=400, detail="urls is required")
    return await _run(request, url_list, format, include_raw, max_chars, cache, strategy, timeout)


@router.post("")
async def extract_post(request: Request, body: ExtractBody):
    return await _run(request, body.urls, body.format, body.include_raw, body.max_chars,
                      body.cache, body.strategy, body.timeout)
```

`src/searchhub/api/routes_providers.py`:
```python
from fastapi import APIRouter, Depends, Request

from searchhub.api.auth import require_token

router = APIRouter(prefix="/v1/providers", tags=["providers"], dependencies=[Depends(require_token)])


@router.get("")
async def list_providers(request: Request):
    return {"providers": request.app.state.engine.provider_status()}
```

- [ ] **Step 4: 更新 config 模型与 app**

`src/searchhub/config.py` 追加：
```python
class TokenEntry(BaseModel):
    name: str
    token_hash: str


class AuthConfig(BaseModel):
    tokens: list[TokenEntry] = Field(default_factory=list)


class AppConfig(BaseModel):
    strategy: StrategyConfig = StrategyConfig()
    cache: CacheConfig = CacheConfig()
    auth: AuthConfig = AuthConfig()
    providers: list[ProviderConfig] = Field(default_factory=list)
```

`src/searchhub/api/app.py`（整体替换）:
```python
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI

from searchhub import __version__
from searchhub.api.routes_extract import router as extract_router
from searchhub.api.routes_health import router as health_router
from searchhub.api.routes_providers import router as providers_router
from searchhub.api.routes_search import router as search_router
from searchhub.config import ConfigService
from searchhub.orchestrator import SearchHubEngine
from searchhub.storage.cache import CacheRepo


def create_app(data_dir: Path | None = None) -> FastAPI:
    data_dir = Path(data_dir) if data_dir else Path.cwd() / "data"

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        config = ConfigService(data_dir)
        config.load()
        cache = CacheRepo(data_dir / "cache.db")
        http = httpx.AsyncClient(timeout=60)
        engine = SearchHubEngine(config, cache, http)
        engine.maybe_reload()
        app.state.engine = engine
        app.state.http = http
        yield
        await http.aclose()
        await cache.close()

    app = FastAPI(title="SearchHub", version=__version__, lifespan=lifespan)
    app.include_router(health_router)
    app.include_router(search_router)
    app.include_router(extract_router)
    app.include_router(providers_router)
    return app
```

- [ ] **Step 5: 运行确认通过**

Run: `.venv/bin/pytest tests/ -v`
Expected: 全部 PASS（含旧任务回归）

- [ ] **Step 6: 提交**

```bash
git add src/searchhub tests
git commit -m "feat: REST API with token auth, search/extract/providers endpoints"
```

---

### Task 16: 收尾——README 与冒烟验证

**Files:**
- Modify: `README.md`
- Test: 手动冒烟（无自动化测试文件）

- [ ] **Step 1: 写 README 快速开始**

`README.md`（替换占位）：
```markdown
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

## 测试

```bash
.venv/bin/pytest
```
```

- [ ] **Step 2: 冒烟验证**

Run（真实 ddg 库、无网络云依赖的端到端）:
```bash
SEARCHHUB_DATA=/tmp/searchhub-smoke .venv/bin/python -m searchhub &
curl -s localhost:8000/healthz
curl -s "localhost:8000/v1/search?q=python" -H "Authorization: Bearer <token>"
kill %1
```
Expected: healthz 200；search 返回统一形状（若无配置供应商则 `success: false` 且错误说明清晰）

- [ ] **Step 3: 全量回归**

Run: `.venv/bin/pytest -v`
Expected: 全绿

- [ ] **Step 4: 提交**

```bash
git add README.md
git commit -m "docs: quickstart and API examples for M1"
```

---

## Self-Review

- **Spec 覆盖**：M1 范围（注册表/Key 池/三种策略/缓存/REST/config+secrets/测试）全覆盖：Task 4=Key 池，Task 5=注册表，Task 6=合并，Task 7=策略，Task 8-12=六个 adapter，Task 13=缓存，Task 14=orchestrator，Task 15=REST+鉴权，Task 2=配置。hermes 契约形状（`data.web[].title/url/description/position`、错误 `{"success": false, "error"}`、单 URL 提取失败带 error 字段）在 Task 15 测试中锁定。密钥掩码/脱敏：KeyPool.status 掩码（Task 4）、密钥不出现在日志/响应。M2 之后的内容（管理 UI/统计面板/MCP/插件）明确不在本计划。
- **占位符扫描**：无 TBD/TODO；每个 adapter 都有完整实现代码与测试代码。
- **类型一致性**：`Outcome`（strategies.py）字段 `provider_id/items/error/took_ms` 在 merge/orchestrator 中一致使用；`Provider` 构造签名 `(cfg, keys, http)` 全 adapter 一致；`merge_search(outcomes, limit, providers)` 与 orchestrator 调用一致；`SearchResponse(success, data, meta)` 与 routes 一致；`include_raw=false` 在 route 层置空 raw_content 与测试一致。
- 已知取舍：`/v1/search`/`/v1/extract` 的非法参数（如 format 非 text/markdown）返回 400 且 body 为 `{"success": false, "error": ...}`；但 Pydantic 层校验失败（如 limit 超界、urls 超 20 个）仍返回 FastAPI 默认 422 `{"detail": ...}`——M1 接受，M2 统一异常处理器时收敛为统一形状。
