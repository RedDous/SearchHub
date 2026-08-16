# SearchHub M2A：管理 API 后端实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 SearchHub M2 的后端管理面：管理员会话鉴权（登录/登出/改密）、供应商与 Key 池的 CRUD 管理 API、策略/缓存/历史设置、调用方 Token 管理、请求历史持久化与查询、统计汇总与时序接口、保留期自动清理。

**Architecture:** 在现有 FastAPI 单体上新增 `/api/admin/*` 路由组（HMAC 签名 Cookie 会话，密钥存 `data/session_secret`）。配置写操作全部走 ConfigService（校验→原子写→热重载）。新增 `history.db`（SQLite）持久化每次 search/extract 请求（引擎内记录，日志失败不影响请求）。保留期清理与缓存过期清理由 lifespan 中的后台任务每小时执行一次。

**Tech Stack:** fastapi、pydantic v2、aiosqlite、stdlib hmac/hashlib.scrypt/secrets；测试 pytest + pytest-asyncio + fastapi TestClient。

## Global Constraints

- 沿用 M1：Python >= 3.11、src/ 布局、提交风格 `feat:`/`fix:`/`chore:`、错误统一 `{"success": false, "error": ...}`（422 由现有 handler 兜底）
- 密钥/密码哈希永不回显：admin config 输出中 `password_hash` 置空、`token_hash` 只给前 8 字符；调用方 token 明文仅在创建响应中返回一次
- 会话 Cookie：`sh_session`，`httponly=True, samesite="lax"`；管理员密码最少 8 字符
- 配置写操作必须走 `ConfigService.save_config`/`save_secrets`（原子写 + 备份 + 热重载），不直接改文件
- 历史记录失败绝不能影响 search/extract 请求本身（try/except 吞掉并 debug 日志）
- 每次请求最多记一条历史；`history.redact_queries=true` 时 query/urls 落盘前 sha1
- 所有新配置段必须有默认值，旧 config.yaml 加载不报错（pydantic 默认值兜底）

## File Structure

```
src/searchhub/
  config.py                  # + AdminConfig/HistoryConfig/TokenEntry 扩展字段、scrypt 哈希、
                             #   save_secrets/add_provider_key/remove_provider_key/session_secret/updated_at
  storage/history.py         # RequestLogRepo（request_log 表、query/summary/timeseries/purge）
  orchestrator.py            # search/extract 单出口重构 + 历史记录 + token_name 参数
  api/
    auth.py                  # 修改：require_token 跳过 revoked
    admin/__init__.py
    admin/session.py         # SessionStore、require_admin、login/logout/change-password
    admin/config_routes.py   # GET /api/admin/config、providers CRUD、/{id}/test、PUT /settings
    admin/keys_routes.py     # GET/POST /api/admin/providers/{id}/keys、DELETE .../keys/{index}
    admin/token_routes.py    # GET/POST/DELETE /api/admin/tokens
    admin/stats_routes.py    # GET /api/admin/history、/stats/summary、/stats/timeseries
  api/app.py                 # lifespan 接线（history/session_store/后台清理任务）+ 挂载 admin 路由
tests/
  test_config_admin.py
  storage/test_history.py
  api/admin/test_session.py
  test_orchestrator_log.py
  api/admin/test_config_routes.py
  api/admin/test_keys_tokens.py
  api/admin/test_stats_routes.py
  conftest.py                # 修改：新增 admin_client fixture
```

---

### Task 1: 配置模型扩展与密钥/密码基础设施

**Files:**
- Modify: `src/searchhub/config.py`
- Test: `tests/test_config_admin.py`

**Interfaces:**
- Produces（config.py）:
  - `class AdminConfig(BaseModel)`: `username: str = "admin"`, `password_hash: str = ""`, `session_ttl_hours: int = Field(default=24, ge=1, le=720)`
  - `class HistoryConfig(BaseModel)`: `retention_days: int = Field(default=30, ge=1, le=3650)`, `redact_queries: bool = False`
  - `class TokenEntry` 增加字段：`id: str = ""`, `created_at: float = 0.0`, `revoked: bool = False`
  - `AppConfig` 增加：`admin: AdminConfig = AdminConfig()`, `history: HistoryConfig = HistoryConfig()`
  - `ConfigService.verify_admin_password(password: str) -> bool`（scrypt 校验，空 hash 返回 False）
  - `ConfigService.set_admin_password(password: str) -> None`（scrypt 哈希 → save_config）
  - `ConfigService.session_secret() -> bytes`（`data/session_secret` 文件，不存在则生成 32 字节 hex，mode 600）
  - `ConfigService.save_secrets(secrets_map: dict[str, str]) -> None`（tmp+os.replace 原子写，mode 600，更新 `_secrets` 与 `_mtime`）
  - `ConfigService.add_provider_key(provider_id: str, key: str) -> None`（空 key 抛 ValueError；键名 `{PID}_KEY_{N}` 取最大 N+1）
  - `ConfigService.remove_provider_key(provider_id: str, index: int) -> None`（越界抛 IndexError；删除后其余 key 保持原编号（不重排，与测试一致））
  - `ConfigService.updated_at -> float`（config.yaml mtime，不存在返回 0.0）

- [ ] **Step 1: 写失败测试**

`tests/test_config_admin.py`:
```python
from pathlib import Path

import pytest

from searchhub.config import ConfigService


@pytest.fixture
def cs(data_dir: Path) -> ConfigService:
    c = ConfigService(data_dir)
    c.load()
    return c


def test_defaults_have_admin_and_history(cs):
    cfg = cs.get()
    assert cfg.admin.username == "admin"
    assert cfg.admin.password_hash == ""
    assert cfg.admin.session_ttl_hours == 24
    assert cfg.history.retention_days == 30
    assert cfg.history.redact_queries is False


def test_password_roundtrip(cs):
    assert cs.verify_admin_password("hunter2") is False
    cs.set_admin_password("hunter2")
    assert cs.verify_admin_password("hunter2") is True
    assert cs.verify_admin_password("wrong") is False
    assert cs.get().admin.password_hash != ""
    assert "hunter2" not in cs.get().admin.password_hash


def test_session_secret_persistent(cs):
    s1 = cs.session_secret()
    s2 = cs.session_secret()
    assert s1 == s2 and len(s1) == 32
    assert oct((cs.data_dir / "session_secret").stat().st_mode & 0o777) == "0o600"


def test_save_secrets_atomic_and_600(cs):
    cs.save_secrets({"EXA_KEY_1": "k1", "TAVILY_KEY_1": "k2"})
    assert cs.secrets()["EXA_KEY_1"] == "k1"
    assert oct((cs.data_dir / "secrets.env").stat().st_mode & 0o777) == "0o600"
    cs2 = ConfigService(cs.data_dir)
    cs2.load()
    assert cs2.provider_keys("exa") == ["k1"]
    assert cs2.provider_keys("tavily") == ["k2"]


def test_add_provider_key_uses_next_index(cs):
    cs.save_secrets({"EXA_KEY_1": "k1", "EXA_KEY_2": "k2", "OTHER_X": "zz"})
    cs.add_provider_key("exa", "k3")
    assert cs.provider_keys("exa") == ["k1", "k2", "k3"]
    assert "OTHER_X" in cs.secrets()
    with pytest.raises(ValueError):
        cs.add_provider_key("exa", "   ")


def test_remove_provider_key_renumbers(cs):
    cs.save_secrets({"EXA_KEY_1": "k1", "EXA_KEY_2": "k2", "EXA_KEY_3": "k3"})
    cs.remove_provider_key("exa", 0)
    assert cs.provider_keys("exa") == ["k2", "k3"]
    assert "EXA_KEY_1" not in cs.secrets()
    assert "EXA_KEY_2" in cs.secrets() and "EXA_KEY_3" in cs.secrets()
    with pytest.raises(IndexError):
        cs.remove_provider_key("exa", 5)


def test_updated_at_after_save(cs):
    before = cs.updated_at
    cfg = cs.get()
    cfg.strategy.default_mode = "rotation"
    cs.save_config(cfg)
    assert cs.updated_at >= before
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/pytest tests/test_config_admin.py -v`
Expected: FAIL（`AdminConfig` 不存在）

- [ ] **Step 3: 实现 config.py 扩展**

在 `src/searchhub/config.py` 顶部 import 追加：
```python
import hashlib
import hmac as _hmac
import secrets as _secrets
```
模块级新增（放在 `_BACKUP_COUNT` 之后）：
```python
def _scrypt_hash(password: str) -> str:
    salt = _secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1)
    return f"scrypt${2 ** 14}${8}${1}${salt.hex()}${digest.hex()}"


def _scrypt_verify(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt_hex, digest_hex = stored.split("$")
        if algo != "scrypt":
            return False
        digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex),
                                n=int(n), r=int(r), p=int(p))
        return _hmac.compare_digest(digest.hex(), digest_hex)
    except Exception:
        return False
```
替换 `TokenEntry` 与 `AuthConfig` 段，并在 `AuthConfig` 之后追加 `AdminConfig`/`HistoryConfig`，扩展 `AppConfig`：
```python
class TokenEntry(BaseModel):
    name: str
    token_hash: str
    id: str = ""
    created_at: float = 0.0
    revoked: bool = False


class AuthConfig(BaseModel):
    tokens: list[TokenEntry] = Field(default_factory=list)


class AdminConfig(BaseModel):
    username: str = "admin"
    password_hash: str = ""
    session_ttl_hours: int = Field(default=24, ge=1, le=720)


class HistoryConfig(BaseModel):
    retention_days: int = Field(default=30, ge=1, le=3650)
    redact_queries: bool = False


class AppConfig(BaseModel):
    strategy: StrategyConfig = StrategyConfig()
    cache: CacheConfig = CacheConfig()
    auth: AuthConfig = AuthConfig()
    admin: AdminConfig = AdminConfig()
    history: HistoryConfig = HistoryConfig()
    providers: list[ProviderConfig] = Field(default_factory=list)
```
`ConfigService` 新增方法（放在 `provider_keys` 之后）：
```python
    def verify_admin_password(self, password: str) -> bool:
        stored = self.get().admin.password_hash
        return bool(stored) and _scrypt_verify(password, stored)

    def set_admin_password(self, password: str) -> None:
        cfg = self.get()
        cfg.admin.password_hash = _scrypt_hash(password)
        self.save_config(cfg)

    def session_secret(self) -> bytes:
        path = self.data_dir / "session_secret"
        if not path.exists():
            path.write_text(_secrets.token_hex(32))
            path.chmod(0o600)
        return bytes.fromhex(path.read_text().strip())

    def save_secrets(self, secrets_map: dict[str, str]) -> None:
        self._secrets = dict(secrets_map)
        tmp = self.secrets_path.with_name(self.secrets_path.name + ".tmp")
        try:
            with tmp.open("w") as f:
                for k, v in sorted(secrets_map.items()):
                    f.write(f"{k}={v}\n")
            os.replace(tmp, self.secrets_path)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        self.secrets_path.chmod(0o600)
        self._mtime = self._stat()

    def add_provider_key(self, provider_id: str, key: str) -> None:
        key = key.strip()
        if not key:
            raise ValueError("key must not be empty")
        prefix = f"{provider_id.upper()}_KEY_"
        secrets_map = dict(self._secrets)
        existing = [k for k in secrets_map if k.startswith(prefix) and k[len(prefix):].isdigit()]
        next_idx = max([int(k[len(prefix):]) for k in existing], default=0) + 1
        secrets_map[f"{prefix}{next_idx}"] = key
        self.save_secrets(secrets_map)

    def remove_provider_key(self, provider_id: str, index: int) -> None:
        keys = self.provider_keys(provider_id)
        if index < 0 or index >= len(keys):
            raise IndexError("key index out of range")
        prefix = f"{provider_id.upper()}_KEY_"
        remaining = keys[:index] + keys[index + 1:]
        secrets_map = {k: v for k, v in self._secrets.items() if not k.startswith(prefix)}
        for i, k in enumerate(remaining, start=1):
            secrets_map[f"{prefix}{i}"] = k
        self.save_secrets(secrets_map)

    @property
    def updated_at(self) -> float:
        try:
            return self.config_path.stat().st_mtime
        except FileNotFoundError:
            return 0.0
```
> 注意：`add_provider_key`/`remove_provider_key` 基于 `provider_keys()`（数字后缀排序）与 `_secrets` 全量重建，保证 `OTHER_X` 这类无关键不被破坏（测试已覆盖）。

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/pytest tests/test_config_admin.py -v`
Expected: PASS（7 passed）

- [ ] **Step 5: 回归**

Run: `.venv/bin/pytest -v`
Expected: 88 passed（旧测试不受影响；TokenEntry 新增字段有默认值）

- [ ] **Step 6: 提交**

```bash
git add src/searchhub/config.py tests/test_config_admin.py
git commit -m "feat: admin/history config models, scrypt password, secrets write methods"
```

---

### Task 2: request_log 存储（RequestLogRepo）

**Files:**
- Create: `src/searchhub/storage/history.py`
- Test: `tests/storage/test_history.py`

**Interfaces:**
- Produces: `class RequestLogRepo`: `__init__(self, db_path: Path)`；`async record(self, entry: dict) -> None`；`async query(self, *, capability=None, provider=None, token=None, from_ts=None, to_ts=None, q=None, limit=100, offset=0) -> list[dict]`；`async purge_before(self, ts: float) -> int`；`async summary(self, since: float) -> dict`；`async timeseries(self, since: float, bucket_s: int) -> list[dict]`；`async close(self)`
- 表 `request_log`：`id INTEGER PK AUTOINCREMENT, ts REAL, capability TEXT, query TEXT, params TEXT, providers TEXT, cache_hit INTEGER, took_ms REAL, result_count INTEGER, success INTEGER, error TEXT, token_name TEXT, response_preview TEXT`；索引 `(ts)`、`(capability)`
- `summary(since)` 返回：`{total, success, cache_hits, avg_took_ms, searches, extracts, success_rate, cache_hit_rate}`（空数据时 success_rate=1.0、cache_hit_rate=0.0）
- `timeseries(since, bucket_s)` 返回按 bucket 升序：`[{ts, count, success, cache_hits, avg_took_ms}]`

- [ ] **Step 1: 写失败测试**

`tests/storage/test_history.py`:
```python
import time
from pathlib import Path

import pytest

from searchhub.storage.history import RequestLogRepo


@pytest.fixture
async def repo(data_dir: Path):
    r = RequestLogRepo(data_dir / "history.db")
    yield r
    await r.close()


def entry(**kw) -> dict:
    base = {"ts": time.time(), "capability": "search", "query": "python",
            "params": "{}", "providers": "exa,ddg", "cache_hit": False,
            "took_ms": 120.0, "result_count": 5, "success": True,
            "error": "", "token_name": "agent1", "response_preview": "a | b"}
    base.update(kw)
    return base


@pytest.mark.asyncio
async def test_record_and_query_all_fields(repo):
    await repo.record(entry())
    rows = await repo.query()
    assert len(rows) == 1
    r = rows[0]
    assert r["capability"] == "search"
    assert r["query"] == "python"
    assert r["cache_hit"] == 0
    assert r["token_name"] == "agent1"
    assert r["success"] == 1


@pytest.mark.asyncio
async def test_query_filters(repo):
    await repo.record(entry(capability="search", providers="exa", token_name="a", ts=1000.0))
    await repo.record(entry(capability="extract", providers="ddg", token_name="b", ts=2000.0))
    await repo.record(entry(capability="extract", providers="exa", token_name="b", ts=3000.0))
    assert len(await repo.query(capability="extract")) == 2
    assert len(await repo.query(provider="exa")) == 2
    assert len(await repo.query(token="a")) == 1
    assert len(await repo.query(from_ts=1500.0, to_ts=2500.0)) == 1
    assert len(await repo.query(q="python")) == 3
    assert len(await repo.query(q="nothing")) == 0
    assert len(await repo.query(limit=2)) == 2
    assert len(await repo.query(limit=1, offset=1)) == 1


@pytest.mark.asyncio
async def test_purge_before(repo):
    await repo.record(entry(ts=100.0))
    await repo.record(entry(ts=200.0))
    assert await repo.purge_before(150.0) == 1
    assert len(await repo.query()) == 1


@pytest.mark.asyncio
async def test_summary(repo):
    await repo.record(entry(capability="search", cache_hit=True, took_ms=100.0))
    await repo.record(entry(capability="search", cache_hit=False, took_ms=300.0, success=False,
                            error="boom"))
    await repo.record(entry(capability="extract", took_ms=200.0))
    s = await repo.summary(since=0.0)
    assert s["total"] == 3
    assert s["success"] == 2
    assert s["cache_hits"] == 1
    assert s["searches"] == 2
    assert s["extracts"] == 1
    assert s["success_rate"] == round(2 / 3, 3)
    assert s["avg_took_ms"] == round(200.0, 1)


@pytest.mark.asyncio
async def test_timeseries_buckets(repo):
    await repo.record(entry(ts=100.0, cache_hit=True))
    await repo.record(entry(ts=3500.0))
    await repo.record(entry(ts=3700.0))
    rows = await repo.timeseries(since=0.0, bucket_s=3600)
    assert [r["ts"] for r in rows] == [0, 3600]
    assert rows[0]["count"] == 1 and rows[0]["cache_hits"] == 1
    assert rows[1]["count"] == 2
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/pytest tests/storage/test_history.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现**

`src/searchhub/storage/history.py`:
```python
from __future__ import annotations

from pathlib import Path

from searchhub.storage.db import open_db

_SCHEMA = """
CREATE TABLE IF NOT EXISTS request_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    capability TEXT NOT NULL,
    query TEXT NOT NULL DEFAULT '',
    params TEXT NOT NULL DEFAULT '{}',
    providers TEXT NOT NULL DEFAULT '',
    cache_hit INTEGER NOT NULL DEFAULT 0,
    took_ms REAL NOT NULL DEFAULT 0,
    result_count INTEGER NOT NULL DEFAULT 0,
    success INTEGER NOT NULL DEFAULT 1,
    error TEXT NOT NULL DEFAULT '',
    token_name TEXT NOT NULL DEFAULT '',
    response_preview TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_request_log_ts ON request_log (ts);
CREATE INDEX IF NOT EXISTS idx_request_log_cap ON request_log (capability);
"""


class RequestLogRepo:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self._conn = None

    async def _conn_ensure(self):
        if self._conn is None:
            self._conn = await open_db(self.db_path)
            await self._conn.executescript(_SCHEMA)
            await self._conn.commit()
        return self._conn

    async def record(self, entry: dict) -> None:
        conn = await self._conn_ensure()
        await conn.execute(
            "INSERT INTO request_log (ts, capability, query, params, providers, cache_hit, "
            "took_ms, result_count, success, error, token_name, response_preview) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (entry["ts"], entry["capability"], entry["query"], entry["params"],
             entry["providers"], int(entry["cache_hit"]), entry["took_ms"],
             entry["result_count"], int(entry["success"]), entry["error"],
             entry["token_name"], entry["response_preview"]),
        )
        await conn.commit()

    async def query(self, *, capability: str | None = None, provider: str | None = None,
                    token: str | None = None, from_ts: float | None = None,
                    to_ts: float | None = None, q: str | None = None,
                    limit: int = 100, offset: int = 0) -> list[dict]:
        clauses: list[str] = []
        args: list = []
        if capability:
            clauses.append("capability = ?")
            args.append(capability)
        if provider:
            clauses.append("providers LIKE ?")
            args.append(f"%{provider}%")
        if token:
            clauses.append("token_name = ?")
            args.append(token)
        if from_ts is not None:
            clauses.append("ts >= ?")
            args.append(from_ts)
        if to_ts is not None:
            clauses.append("ts <= ?")
            args.append(to_ts)
        if q:
            clauses.append("query LIKE ?")
            args.append(f"%{q}%")
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        conn = await self._conn_ensure()
        cur = await conn.execute(
            f"SELECT * FROM request_log {where} ORDER BY ts DESC LIMIT ? OFFSET ?",
            (*args, int(limit), int(offset)),
        )
        rows = await cur.fetchall()
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in rows]

    async def purge_before(self, ts: float) -> int:
        conn = await self._conn_ensure()
        cur = await conn.execute("DELETE FROM request_log WHERE ts < ?", (ts,))
        await conn.commit()
        return cur.rowcount or 0

    async def summary(self, since: float) -> dict:
        conn = await self._conn_ensure()
        cur = await conn.execute(
            """SELECT COUNT(*) AS total, SUM(success) AS ok, SUM(cache_hit) AS cached,
                      AVG(took_ms) AS avg_ms,
                      SUM(CASE WHEN capability = 'search' THEN 1 ELSE 0 END) AS searches,
                      SUM(CASE WHEN capability = 'extract' THEN 1 ELSE 0 END) AS extracts
               FROM request_log WHERE ts >= ?""",
            (since,),
        )
        row = await cur.fetchone()
        total = row[0] or 0
        return {
            "total": total,
            "success": row[1] or 0,
            "cache_hits": row[2] or 0,
            "avg_took_ms": round(row[3] or 0.0, 1),
            "searches": row[4] or 0,
            "extracts": row[5] or 0,
            "success_rate": round((row[1] or 0) / total, 3) if total else 1.0,
            "cache_hit_rate": round((row[2] or 0) / total, 3) if total else 0.0,
        }

    async def timeseries(self, since: float, bucket_s: int) -> list[dict]:
        conn = await self._conn_ensure()
        cur = await conn.execute(
            """SELECT CAST(ts / ? AS INTEGER) * ? AS bucket, COUNT(*) AS total,
                      SUM(success) AS ok, SUM(cache_hit) AS cached, AVG(took_ms) AS avg_ms
               FROM request_log WHERE ts >= ? GROUP BY bucket ORDER BY bucket""",
            (bucket_s, bucket_s, since),
        )
        rows = await cur.fetchall()
        return [{"ts": r[0], "count": r[1] or 0, "success": r[2] or 0,
                 "cache_hits": r[3] or 0, "avg_took_ms": round(r[4] or 0.0, 1)} for r in rows]

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/pytest tests/storage/test_history.py -v`
Expected: PASS（6 passed）

- [ ] **Step 5: 提交**

```bash
git add src/searchhub/storage/history.py tests/storage/test_history.py
git commit -m "feat: request log repository with query, summary, timeseries"
```

---

### Task 3: 管理员会话鉴权（登录/登出/改密）

**Files:**
- Create: `src/searchhub/api/admin/__init__.py`
- Create: `src/searchhub/api/admin/session.py`
- Modify: `tests/conftest.py`（新增 `admin_client` fixture）
- Test: `tests/api/admin/test_session.py`

**Interfaces:**
- Produces（session.py）:
  - `COOKIE_NAME = "sh_session"`
  - `class SessionStore`: `__init__(self, secret: bytes)`；`create(self, username: str, ttl_hours: int) -> str`（payload `{"u", "exp"}` base64url + hmac-sha256 签名，格式 `b64.sig`）；`verify(self, token: str) -> str | None`
  - `async def require_admin(request: Request, sh_session: str | None = Cookie(default=None)) -> None`（读 `app.state.session_store`，无效/过期抛 HTTPException 401 "unauthorized"）
  - `router = APIRouter(prefix="/api/admin", tags=["admin"])`，路由：
    - `POST /api/admin/login` body `{username, password}`：成功 → `response.set_cookie(COOKIE_NAME, token, httponly=True, samesite="lax", max_age=ttl*3600)`，返回 `{"success": True, "data": {"username"}}`；失败 401 "invalid credentials"
    - `POST /api/admin/logout`：`response.delete_cookie(COOKIE_NAME)` → `{"success": True}`
    - `POST /api/admin/change-password` body `{old_password, new_password(min 8)}`（依赖 require_admin）：旧密错误 400 "old password is incorrect"；成功 → `{"success": True}`
- 依赖 `app.state.session_store`（Task 8 在 lifespan 设置）；依赖 `app.state.engine.config`（ConfigService）

- [ ] **Step 1: 写失败测试**

`tests/api/admin/test_session.py`:
```python
import pytest
from fastapi.testclient import TestClient

from searchhub.api.admin.session import SessionStore
from searchhub.api.app import create_app
from searchhub.config import ConfigService


def make_app_client(data_dir, password="testpass123"):
    cs = ConfigService(data_dir)
    cs.load()
    cs.set_admin_password(password)
    app = create_app(data_dir)
    return TestClient(app)


def test_login_logout_flow(data_dir):
    with make_app_client(data_dir) as c:
        r = c.post("/api/admin/login", json={"username": "admin", "password": "wrong"})
        assert r.status_code == 401
        r = c.post("/api/admin/login", json={"username": "admin", "password": "testpass123"})
        assert r.status_code == 200
        assert r.json()["success"] is True
        assert c.cookies.get("sh_session")
        r = c.post("/api/admin/logout")
        assert r.status_code == 200
        assert c.cookies.get("sh_session") is None


def test_admin_routes_require_session(data_dir):
    with make_app_client(data_dir) as c:
        r = c.get("/api/admin/config")
        assert r.status_code == 401
        assert r.json()["error"] == "unauthorized"


def test_change_password(data_dir):
    with make_app_client(data_dir) as c:
        c.post("/api/admin/login", json={"username": "admin", "password": "testpass123"})
        r = c.post("/api/admin/change-password",
                   json={"old_password": "nope", "new_password": "newpass123"})
        assert r.status_code == 400
        r = c.post("/api/admin/change-password",
                   json={"old_password": "testpass123", "new_password": "newpass123"})
        assert r.status_code == 200
        c.post("/api/admin/logout")
        r = c.post("/api/admin/login", json={"username": "admin", "password": "testpass123"})
        assert r.status_code == 401
        r = c.post("/api/admin/login", json={"username": "admin", "password": "newpass123"})
        assert r.status_code == 200


def test_short_password_rejected(data_dir):
    with make_app_client(data_dir) as c:
        c.post("/api/admin/login", json={"username": "admin", "password": "testpass123"})
        r = c.post("/api/admin/change-password",
                   json={"old_password": "testpass123", "new_password": "short"})
        assert r.status_code == 422


def test_session_store_signs_and_verifies():
    store = SessionStore(b"x" * 32)
    token = store.create("admin", ttl_hours=1)
    assert store.verify(token) == "admin"
    assert store.verify(token + "x") is None
    assert store.verify("garbage") is None


def test_expired_session_rejected():
    store = SessionStore(b"x" * 32)
    token = store.create("admin", ttl_hours=-1)
    assert store.verify(token) is None
```

`tests/conftest.py` 追加 fixture（放在 `client` fixture 之后；注意当前 `app.py` 未设置 `app.state.data_dir`，fixture 直接用自己的 `data_dir` fixture）：
```python
@pytest.fixture
def admin_client(data_dir):
    from fastapi.testclient import TestClient

    from searchhub.api.app import create_app
    from searchhub.config import ConfigService

    cs = ConfigService(data_dir)
    cs.load()
    cs.set_admin_password("testpass123")
    app = create_app(data_dir)
    with TestClient(app) as c:
        r = c.post("/api/admin/login", json={"username": "admin", "password": "testpass123"})
        assert r.status_code == 200, r.text
        yield c
```
> 注意：TestClient 进入时 lifespan 才跑。lifespan 内会执行"首次无密码→设默认密码"逻辑（Task 8 实现），此处已预先 `set_admin_password`，故 lifespan 不会覆盖。

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/pytest tests/api/admin/test_session.py -v`
Expected: FAIL（模块不存在 / 路由 404）

- [ ] **Step 3: 实现**

`src/searchhub/api/admin/__init__.py`:
```python
```

`src/searchhub/api/admin/session.py`:
```python
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

COOKIE_NAME = "sh_session"


class SessionStore:
    def __init__(self, secret: bytes):
        self._secret = secret

    def create(self, username: str, ttl_hours: int) -> str:
        payload = {"u": username, "exp": time.time() + ttl_hours * 3600}
        b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
        sig = hmac.new(self._secret, b64.encode(), hashlib.sha256).hexdigest()
        return f"{b64}.{sig}"

    def verify(self, token: str) -> str | None:
        try:
            b64, sig = token.rsplit(".", 1)
            if not hmac.compare_digest(
                hmac.new(self._secret, b64.encode(), hashlib.sha256).hexdigest(), sig
            ):
                return None
            raw = json.loads(base64.urlsafe_b64decode(b64 + "=" * (-len(b64) % 4)))
            if raw.get("exp", 0) < time.time():
                return None
            return raw.get("u") or None
        except Exception:
            return None


router = APIRouter(prefix="/api/admin", tags=["admin"])


class LoginBody(BaseModel):
    username: str
    password: str


class ChangePasswordBody(BaseModel):
    old_password: str
    new_password: str = Field(min_length=8, max_length=128)


async def require_admin(request: Request,
                        sh_session: str | None = Cookie(default=None)) -> None:
    store: SessionStore = request.app.state.session_store
    if not sh_session or store.verify(sh_session) is None:
        raise HTTPException(status_code=401, detail="unauthorized")


@router.post("/login")
async def login(body: LoginBody, request: Request, response: Response):
    cfg = request.app.state.engine.config
    app_cfg = cfg.get()
    if body.username != app_cfg.admin.username or not cfg.verify_admin_password(body.password):
        raise HTTPException(status_code=401, detail="invalid credentials")
    token = request.app.state.session_store.create(
        app_cfg.admin.username, app_cfg.admin.session_ttl_hours)
    response.set_cookie(COOKIE_NAME, token, httponly=True, samesite="lax",
                        max_age=app_cfg.admin.session_ttl_hours * 3600)
    return {"success": True, "data": {"username": app_cfg.admin.username}}


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(COOKIE_NAME)
    return {"success": True}


@router.post("/change-password", dependencies=[Depends(require_admin)])
async def change_password(body: ChangePasswordBody, request: Request):
    cfg = request.app.state.engine.config
    if not cfg.verify_admin_password(body.old_password):
        raise HTTPException(status_code=400, detail="old password is incorrect")
    cfg.set_admin_password(body.new_password)
    return {"success": True}
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/pytest tests/api/admin/test_session.py -v`
Expected: PASS（6 passed）

- [ ] **Step 5: 提交**

```bash
git add src/searchhub/api/admin tests/conftest.py tests/api/admin/test_session.py
git commit -m "feat: admin session auth with login/logout/change-password"
```

---

### Task 4: 引擎历史记录（单出口重构 + token_name）

**Files:**
- Modify: `src/searchhub/orchestrator.py`
- Test: `tests/test_orchestrator_log.py`

**Interfaces:**
- Consumes: `RequestLogRepo`（Task 2）、`cfg.history.redact_queries`
- Produces:
  - `SearchHubEngine.__init__(self, config, cache, http, history: RequestLogRepo | None = None)`
  - `async search(self, query, limit=5, providers=None, strategy=None, cache=True, timeout=None, *, token_name: str = "") -> SearchResponse`（行为与 M1 完全一致，仅重构为单出口 + 记录历史）
  - `async extract(self, urls, fmt="markdown", max_chars=15000, strategy=None, cache=True, timeout=None, *, token_name: str = "") -> ExtractResponse`
  - 私有：`async def _log(self, resp, *, capability: str, query: str, params: dict, providers_used: str, token_name: str) -> None`（内部 try/except，失败仅 debug 日志）
  - 私有：`def _preview(self, resp, capability: str) -> str`（search: `title|url` 前 20 条；extract: `url|ok|error` 前 20 条；`" || "` 连接截断 2000 字符）
- 记录字段：`ts=time.time()`、`query`（redact 时 sha1 hex）、`params`（json.dumps 截断 500）、`providers`（逗号连接的 outcome provider id）、`cache_hit`、`took_ms`（meta）、`result_count`、`success`、`error`、`token_name`、`response_preview`

- [ ] **Step 1: 写失败测试**

`tests/test_orchestrator_log.py`（复用 Task 14 的 FakeProvider 模式）:
```python
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from searchhub.config import ConfigService, ProviderConfig
from searchhub.models import SearchItem
from searchhub.orchestrator import SearchHubEngine
from searchhub.storage.history import RequestLogRepo


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
    engine = SearchHubEngine(cs, None, httpx.AsyncClient(),
                             history=RequestLogRepo(data_dir / "history.db"))
    engine._registry = {"fake": FakeProvider("fake", fail=fail)}
    engine._version = cs.config_version
    return engine


@pytest.mark.asyncio
async def test_search_records_history(data_dir):
    eng = make_engine(data_dir)
    resp = await eng.search("python", limit=3, token_name="agent-x")
    rows = await eng.history.query()
    assert len(rows) == 1
    r = rows[0]
    assert r["capability"] == "search"
    assert r["query"] == "python"
    assert r["token_name"] == "agent-x"
    assert r["success"] == 1
    assert r["result_count"] == 1
    assert r["cache_hit"] == 0
    assert "fake" in r["providers"]
    assert "python" in r["response_preview"]


@pytest.mark.asyncio
async def test_search_records_failure(data_dir):
    eng = make_engine(data_dir, fail=True)
    resp = await eng.search("python", token_name="a")
    assert resp.success is False
    rows = await eng.history.query()
    assert rows[0]["success"] == 0
    assert "boom" in rows[0]["error"]


@pytest.mark.asyncio
async def test_extract_records_history(data_dir):
    eng = make_engine(data_dir)
    await eng.extract(["https://a.com"], token_name="b")
    rows = await eng.history.query()
    assert rows[0]["capability"] == "extract"
    assert rows[0]["query"] == "https://a.com"
    assert rows[0]["token_name"] == "b"


@pytest.mark.asyncio
async def test_redact_queries(data_dir):
    eng = make_engine(data_dir)
    eng.config.get().history.redact_queries = True
    await eng.search("secret-query", token_name="a")
    rows = await eng.history.query()
    assert rows[0]["query"] != "secret-query"
    assert len(rows[0]["query"]) == 40  # sha1 hex


@pytest.mark.asyncio
async def test_log_failure_does_not_break_request(data_dir, monkeypatch):
    eng = make_engine(data_dir)

    async def broken_record(self, entry):
        raise RuntimeError("disk full")

    monkeypatch.setattr(eng.history, "record", broken_record)
    resp = await eng.search("python", token_name="a")
    assert resp.success is True


@pytest.mark.asyncio
async def test_no_history_engine_works(data_dir):
    cs = ConfigService(data_dir)
    cs.load()
    cfg = cs.get()
    cfg.providers = [ProviderConfig(id="fake", capabilities=["search", "extract"])]
    cs.save_config(cfg)
    eng = SearchHubEngine(cs, None, httpx.AsyncClient())
    eng._registry = {"fake": FakeProvider("fake")}
    eng._version = cs.config_version
    resp = await eng.search("python")
    assert resp.success is True
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/pytest tests/test_orchestrator_log.py -v`
Expected: FAIL（`history` 参数不存在）

- [ ] **Step 3: 重构 orchestrator.py**

import 追加与 `__init__` 修改：
```python
import hashlib
import logging
...
from searchhub.storage.cache import CacheRepo
from searchhub.storage.history import RequestLogRepo

logger = logging.getLogger(__name__)


class SearchHubEngine:
    def __init__(self, config: ConfigService, cache: CacheRepo | None,
                 http: httpx.AsyncClient, history: RequestLogRepo | None = None):
        self.config = config
        self.cache = cache
        self.http = http
        self.history = history
        self._registry: dict[str, Provider] = {}
        self._version = -1
        self.stats: dict[str, dict[str, Any]] = {}
```
`search` 方法整体替换为单出口版本：
```python
    async def search(self, query: str, limit: int = 5, providers: str | None = None,
                     strategy: str | None = None, cache: bool = True,
                     timeout: float | None = None, *, token_name: str = "") -> SearchResponse:
        start = time.monotonic()
        cfg = self.config.get()
        providers_list = self._filter(self._registry_for("search"), providers)
        mode = strategy or cfg.strategy.default_mode
        t = timeout or cfg.strategy.timeout_s
        cache_key = search_cache_key(query, limit, providers or "all", mode)
        outcomes: list[Outcome] = []
        resp: SearchResponse | None = None
        if not providers_list:
            resp = SearchResponse(success=False, data=SearchData(web=[]),
                                  error="no search provider enabled",
                                  meta={"took_ms": 0})
        elif self.cache and cache:
            hit = await self.cache.get(cache_key)
            if hit is not None:
                items = [SearchItem(**d) for d in json.loads(hit)]
                resp = SearchResponse(success=True, data=SearchData(web=items),
                                      meta={"took_ms": 0, "cached": True})
        if resp is None:
            if mode == "fanout":
                calls = [(p, p.search(query, min(limit, p.cfg.max_results)))
                         for p in providers_list]
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
            if all(o.error for o in outcomes):
                details = "; ".join(f"{o.provider_id}: {o.error}" for o in outcomes)
                resp = SearchResponse(success=False, data=SearchData(web=[]), error=details,
                                      meta={"took_ms": (time.monotonic() - start) * 1000})
            else:
                merged = merge_search(outcomes, limit, self._registry)
                if self.cache and cache:
                    await self.cache.put(cache_key,
                                         json.dumps([i.model_dump() for i in merged]),
                                         cfg.cache.search_ttl_s)
                resp = SearchResponse(success=True, data=SearchData(web=merged),
                                      meta={"took_ms": (time.monotonic() - start) * 1000,
                                            "cached": False,
                                            "provider_stats": {
                                                o.provider_id: {
                                                    "success": o.error is None,
                                                    "took_ms": round(o.took_ms, 1),
                                                    "count": len(o.items) if o.items else 0,
                                                    "error": o.error}
                                                for o in outcomes}})
        await self._log(resp, capability="search", query=query,
                        params={"limit": limit, "providers": providers, "strategy": mode,
                                "cache": cache, "timeout": timeout},
                        providers_used=",".join(sorted({o.provider_id for o in outcomes})),
                        token_name=token_name)
        return resp
```
`extract` 方法同样改为单出口（在 `_record` 循环后、返回前插入 `_log`；分支结构保持，仅把两处 `return ExtractResponse(...)` 改为 `resp = ...`，最后统一 `await self._log(...)` + `return resp`；query 参数为 `",".join(urls)`，params 为 `{"fmt": fmt, "max_chars": max_chars, "strategy": mode, "cache": cache, "timeout": timeout}`，result_count 为 `len(resp.data)`）。方法末尾追加两个私有方法：
```python
    async def _log(self, resp, *, capability: str, query: str, params: dict,
                   providers_used: str, token_name: str) -> None:
        cfg = self.config.get()
        if self.history is None:
            return
        try:
            if cfg.history.redact_queries:
                query = hashlib.sha1(query.encode()).hexdigest()
            meta = resp.meta if hasattr(resp, "meta") else {}
            await self.history.record({
                "ts": time.time(),
                "capability": capability,
                "query": query,
                "params": json.dumps(params, ensure_ascii=False)[:500],
                "providers": providers_used,
                "cache_hit": bool(meta.get("cached", False)),
                "took_ms": meta.get("took_ms", 0.0),
                "result_count": len(resp.data.web) if capability == "search" else len(resp.data),
                "success": resp.success,
                "error": resp.error or "",
                "token_name": token_name,
                "response_preview": self._preview(resp, capability),
            })
        except Exception as e:
            logger.debug("request log failed: %s", e)

    def _preview(self, resp, capability: str) -> str:
        if capability == "search":
            parts = [f"{i.title}|{i.url}" for i in resp.data.web[:20]]
        else:
            parts = [f"{i.url}|{'ok' if i.error is None else i.error}" for i in resp.data[:20]]
        return " || ".join(parts)[:2000]
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/pytest tests/test_orchestrator_log.py -v`
Expected: PASS（6 passed）

- [ ] **Step 5: 回归**

Run: `.venv/bin/pytest -v`
Expected: 94 passed（88 + 6；旧 orchestrator 测试 `make_engine` 用位置参数不受影响）

- [ ] **Step 6: 提交**

```bash
git add src/searchhub/orchestrator.py tests/test_orchestrator_log.py
git commit -m "feat: record search/extract history in engine with redaction"
```

---

### Task 5: 管理路由——配置查看、供应商 CRUD、连接测试、设置

**Files:**
- Create: `src/searchhub/api/admin/config_routes.py`
- Test: `tests/api/admin/test_config_routes.py`

**Interfaces:**
- Consumes: `require_admin`（Task 3）、`ConfigService`、`PROVIDER_CLASSES`（`searchhub.providers`）、`httpx`
- Produces: `router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])`，路由：
  - `GET /api/admin/config` → `{"success": True, "data": {"config": <AppConfig dump, password_hash 置空、token_hash 前8+****>, "config_version": int, "updated_at": float}}`（先 `svc.maybe_reload()`）
  - `POST /api/admin/providers` body `ProviderConfig`：重复 id → 409 "provider X already exists"；成功 `{"success": True}`
  - `PUT /api/admin/providers/{provider_id}` body `ProviderConfig`：body.id 与 path 不一致 → 400；不存在 → 404；成功 `{"success": True}`
  - `DELETE /api/admin/providers/{provider_id}`：不存在 → 404；成功 `{"success": True}`
  - `POST /api/admin/providers/{provider_id}/test`：不在配置或非内置 adapter → 404；用当前配置+密钥新建 provider 实例（新 httpx client），search 能力优先探活（`search("searchhub connection test", 1)`），否则 extract（`["https://example.com"]`, max_chars=200），`asyncio.wait_for(..., 10)`；返回 `{"success": bool, "data": {"capability", "count", "took_ms"}}` 或 `{"success": False, "error": "Type: msg"}`（测试结束关闭 client）
  - `PUT /api/admin/settings` body `{strategy?: StrategyConfig, cache?: CacheConfig, history?: HistoryConfig}`（部分更新）→ `{"success": True, "data": {"config_version": int}}`

- [ ] **Step 1: 写失败测试**

`tests/api/admin/test_config_routes.py`:
```python
import pytest


def test_config_shows_masked_secrets(admin_client):
    r = admin_client.get("/api/admin/config")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["config_version"] >= 0
    assert data["config"]["admin"]["password_hash"] == ""
    for t in data["config"]["auth"]["tokens"]:
        assert "****" in t["token_hash"]


def test_provider_crud(admin_client):
    body = {"id": "ddg", "capabilities": ["search"], "enabled": True, "weight": 5}
    r = admin_client.post("/api/admin/providers", json=body)
    assert r.status_code == 200 and r.json()["success"] is True
    r = admin_client.post("/api/admin/providers", json=body)
    assert r.status_code == 409
    r = admin_client.put("/api/admin/providers/ddg", json={**body, "weight": 9})
    assert r.status_code == 200
    cfg = admin_client.get("/api/admin/config").json()["data"]["config"]
    assert cfg["providers"][0]["weight"] == 9
    r = admin_client.put("/api/admin/providers/ddg", json={**body, "id": "exa"})
    assert r.status_code == 400
    r = admin_client.delete("/api/admin/providers/ddg")
    assert r.status_code == 200
    r = admin_client.delete("/api/admin/providers/ddg")
    assert r.status_code == 404
    cfg = admin_client.get("/api/admin/config").json()["data"]["config"]
    assert cfg["providers"] == []


def test_provider_validation_rejected(admin_client):
    r = admin_client.post("/api/admin/providers",
                          json={"id": "bad", "capabilities": ["crawl"]})
    assert r.status_code == 400  # save_config 的 capabilities 校验


def test_provider_test_unknown(admin_client):
    r = admin_client.post("/api/admin/providers/nope/test")
    assert r.status_code == 404


def test_provider_test_search_probe(admin_client):
    from searchhub.models import SearchItem
    from searchhub.providers.ddg import DdgProvider

    original = DdgProvider.search

    async def fake_search(self, query, limit):
        return [SearchItem(title="t", url="https://x.com", provider="ddg")]

    DdgProvider.search = fake_search
    try:
        admin_client.post("/api/admin/providers",
                          json={"id": "ddg", "capabilities": ["search"]})
        r = admin_client.post("/api/admin/providers/ddg/test")
    finally:
        DdgProvider.search = original
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"]["capability"] == "search"
    assert body["data"]["count"] == 1


def test_settings_partial_update(admin_client):
    r = admin_client.put("/api/admin/settings",
                         json={"cache": {"enabled": False, "search_ttl_s": 60}})
    assert r.status_code == 200
    cfg = admin_client.get("/api/admin/config").json()["data"]["config"]
    assert cfg["cache"]["enabled"] is False
    assert cfg["cache"]["search_ttl_s"] == 60
    assert cfg["strategy"]["default_mode"] == "fanout"  # 未动
    r = admin_client.put("/api/admin/settings", json={"strategy": {"default_mode": "bad"}})
    assert r.status_code == 422


def test_settings_requires_auth(data_dir):
    from fastapi.testclient import TestClient

    from searchhub.api.app import create_app
    from searchhub.config import ConfigService

    cs = ConfigService(data_dir)
    cs.load()
    cs.set_admin_password("testpass123")
    with TestClient(create_app(data_dir)) as c:
        assert c.get("/api/admin/config").status_code == 401
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/pytest tests/api/admin/test_config_routes.py -v`
Expected: FAIL（模块不存在 / 404）

- [ ] **Step 3: 实现**

`src/searchhub/api/admin/config_routes.py`:
```python
from __future__ import annotations

import asyncio
import time

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from searchhub.api.admin.session import require_admin
from searchhub.config import CacheConfig, HistoryConfig, ProviderConfig, StrategyConfig
from searchhub.providers import PROVIDER_CLASSES

router = APIRouter(prefix="/api/admin", tags=["admin"],
                   dependencies=[Depends(require_admin)])


class SettingsBody(BaseModel):
    strategy: StrategyConfig | None = None
    cache: CacheConfig | None = None
    history: HistoryConfig | None = None


@router.get("/config")
async def get_config(request: Request):
    svc = request.app.state.engine.config
    svc.maybe_reload()
    cfg = svc.get()
    data = cfg.model_dump(mode="json")
    data["admin"]["password_hash"] = ""
    for t in data["auth"]["tokens"]:
        t["token_hash"] = t["token_hash"][:8] + "****"
    return {"success": True, "data": {"config": data,
                                      "config_version": svc.config_version,
                                      "updated_at": svc.updated_at}}


@router.post("/providers")
async def create_provider(body: ProviderConfig, request: Request):
    svc = request.app.state.engine.config
    if svc.get().provider(body.id) is not None:
        raise HTTPException(status_code=409, detail=f"provider {body.id} already exists")
    cfg = svc.get()
    cfg.providers.append(body)
    svc.save_config(cfg)
    return {"success": True}


@router.put("/providers/{provider_id}")
async def update_provider(provider_id: str, body: ProviderConfig, request: Request):
    svc = request.app.state.engine.config
    cfg = svc.get()
    idx = next((i for i, p in enumerate(cfg.providers) if p.id == provider_id), None)
    if idx is None:
        raise HTTPException(status_code=404, detail=f"provider {provider_id} not found")
    if body.id != provider_id:
        raise HTTPException(status_code=400, detail="provider id in body must match path")
    cfg.providers[idx] = body
    svc.save_config(cfg)
    return {"success": True}


@router.delete("/providers/{provider_id}")
async def delete_provider(provider_id: str, request: Request):
    svc = request.app.state.engine.config
    cfg = svc.get()
    new = [p for p in cfg.providers if p.id != provider_id]
    if len(new) == len(cfg.providers):
        raise HTTPException(status_code=404, detail=f"provider {provider_id} not found")
    cfg.providers = new
    svc.save_config(cfg)
    return {"success": True}


@router.post("/providers/{provider_id}/test")
async def test_provider(provider_id: str, request: Request):
    svc = request.app.state.engine.config
    svc.maybe_reload()
    pc = svc.get().provider(provider_id)
    cls = PROVIDER_CLASSES.get(provider_id)
    if pc is None or cls is None:
        raise HTTPException(status_code=404,
                            detail=f"provider {provider_id} not found or unsupported")
    keys = svc.provider_keys(provider_id)
    async with httpx.AsyncClient(timeout=10) as http:
        provider = cls(pc, keys, http)
        cap = "search" if "search" in pc.capabilities else "extract"
        try:
            start = time.monotonic()
            if cap == "search":
                items = await asyncio.wait_for(provider.search("searchhub connection test", 1), 10)
            else:
                items = await asyncio.wait_for(
                    provider.extract(["https://example.com"], max_chars=200), 10)
            return {"success": True, "data": {"capability": cap, "count": len(items),
                                              "took_ms": round(
                                                  (time.monotonic() - start) * 1000, 1)}}
        except Exception as e:
            return {"success": False, "error": f"{type(e).__name__}: {e}"}


@router.put("/settings")
async def update_settings(body: SettingsBody, request: Request):
    svc = request.app.state.engine.config
    cfg = svc.get()
    if body.strategy is not None:
        cfg.strategy = body.strategy
    if body.cache is not None:
        cfg.cache = body.cache
    if body.history is not None:
        cfg.history = body.history
    svc.save_config(cfg)
    return {"success": True, "data": {"config_version": svc.config_version}}
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/pytest tests/api/admin/test_config_routes.py -v`
Expected: PASS（8 passed）

- [ ] **Step 5: 提交**

```bash
git add src/searchhub/api/admin/config_routes.py tests/api/admin/test_config_routes.py
git commit -m "feat: admin config view, provider CRUD, connection test, settings"
```

---

### Task 6: 管理路由——Key 管理 + 调用方 Token 管理

**Files:**
- Create: `src/searchhub/api/admin/keys_routes.py`
- Create: `src/searchhub/api/admin/token_routes.py`
- Modify: `src/searchhub/api/auth.py`（`_authorized` 跳过 `revoked`）
- Test: `tests/api/admin/test_keys_tokens.py`

**Interfaces:**
- Consumes: `require_admin`、`ConfigService`、`TokenEntry`
- Produces（keys_routes.py，prefix `/api/admin` + require_admin）：
  - `GET /api/admin/providers/{provider_id}/keys` → `{"success": True, "data": {"keys": [{index, masked, status}]}}`；`masked` 规则与 KeyPool 一致（len>=9: `k[:5]+"****"+k[-4:]`；4<=len<9: `k[:2]+"****"+k[-2:]`；更短 `"****"`）；`status` 取引擎注册表 `provider_status()` 中该 provider 的 keypool 状态（无则 `null`）
  - `POST /api/admin/providers/{provider_id}/keys` body `{key: str}`：空 → 400；成功 `{"success": True}`
  - `DELETE /api/admin/providers/{provider_id}/keys/{index}`：越界 → 404；成功 `{"success": True}`
- Produces（token_routes.py，prefix `/api/admin` + require_admin）：
  - `GET /api/admin/tokens` → `{"success": True, "data": {"tokens": [{id, name, created_at, revoked, hash_prefix}]}}`
  - `POST /api/admin/tokens` body `{name: 1-64}` → 生成 `secrets.token_urlsafe(32)`，存 `token_hash=sha256 hex`，`id=secrets.token_hex(8)`，返回 `{"success": True, "data": {"id", "name", "token"}}`（明文仅此一次）
  - `DELETE /api/admin/tokens/{token_id}`：不存在 → 404；成功 `{"success": True}`
- Produces（auth.py 修改）：`_authorized` 增加 `and not t.revoked`

- [ ] **Step 1: 写失败测试**

`tests/api/admin/test_keys_tokens.py`:
```python
import hashlib

import pytest


def test_keys_list_add_remove(admin_client):
    admin_client.post("/api/admin/providers",
                      json={"id": "exa", "capabilities": ["search", "extract"]})
    r = admin_client.get("/api/admin/providers/exa/keys")
    assert r.json()["data"]["keys"] == []
    r = admin_client.post("/api/admin/providers/exa/keys", json={"key": "  "})
    assert r.status_code == 400
    r = admin_client.post("/api/admin/providers/exa/keys", json={"key": "sekrit-123"})
    assert r.status_code == 200
    r = admin_client.post("/api/admin/providers/exa/keys", json={"key": "sekrit-456"})
    assert r.status_code == 200
    r = admin_client.get("/api/admin/providers/exa/keys")
    keys = r.json()["data"]["keys"]
    assert len(keys) == 2
    assert keys[0]["masked"] == "sekri****3-123"[:5] + "****" + "sekrit-123"[-4:]
    assert "sekrit-123" not in r.text
    r = admin_client.delete("/api/admin/providers/exa/keys/0")
    assert r.status_code == 200
    keys = admin_client.get("/api/admin/providers/exa/keys").json()["data"]["keys"]
    assert len(keys) == 1
    assert keys[0]["masked"].endswith("456")
    r = admin_client.delete("/api/admin/providers/exa/keys/5")
    assert r.status_code == 404


def test_token_create_list_delete(admin_client):
    r = admin_client.get("/api/admin/tokens")
    assert r.json()["data"]["tokens"] == []
    r = admin_client.post("/api/admin/tokens", json={"name": "my-agent"})
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["name"] == "my-agent"
    assert len(body["token"]) >= 32
    token_id = body["id"]
    r = admin_client.get("/api/admin/tokens")
    tokens = r.json()["data"]["tokens"]
    assert len(tokens) == 1
    assert tokens[0]["hash_prefix"] == hashlib.sha256(body["token"].encode()).hexdigest()[:8]
    assert "token" not in tokens[0]  # 明文不回显
    r = admin_client.delete(f"/api/admin/tokens/{token_id}")
    assert r.status_code == 200
    r = admin_client.delete(f"/api/admin/tokens/{token_id}")
    assert r.status_code == 404


def test_created_token_works_on_public_api(admin_client):
    r = admin_client.post("/api/admin/tokens", json={"name": "agent"})
    raw = r.json()["data"]["token"]
    resp = admin_client.get("/v1/search", params={"q": "x"},
                            headers={"Authorization": f"Bearer {raw}"})
    assert resp.status_code == 200  # 无供应商也返回 200 success=false


def test_revoked_token_rejected(admin_client, data_dir):
    from searchhub.config import ConfigService

    r = admin_client.post("/api/admin/tokens", json={"name": "agent"})
    raw = r.json()["data"]["token"]
    token_id = r.json()["data"]["id"]
    resp = admin_client.get("/v1/search", params={"q": "x"},
                            headers={"Authorization": f"Bearer {raw}"})
    assert resp.status_code == 200
    cs = ConfigService(data_dir)
    cs.load()
    cfg = cs.get()
    for t in cfg.auth.tokens:
        if t.id == token_id:
            t.revoked = True
    cs.save_config(cfg)
    resp = admin_client.get("/v1/search", params={"q": "x"},
                            headers={"Authorization": f"Bearer {raw}"})
    assert resp.status_code == 401
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/pytest tests/api/admin/test_keys_tokens.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 keys_routes.py**

`src/searchhub/api/admin/keys_routes.py`:
```python
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from searchhub.api.admin.session import require_admin

router = APIRouter(prefix="/api/admin", tags=["admin"],
                   dependencies=[Depends(require_admin)])


class KeyBody(BaseModel):
    key: str


def _mask(key: str) -> str:
    if len(key) >= 9:
        return key[:5] + "****" + key[-4:]
    if len(key) >= 4:
        return key[:2] + "****" + key[-2:]
    return "****"


@router.get("/providers/{provider_id}/keys")
async def list_keys(provider_id: str, request: Request):
    svc = request.app.state.engine.config
    keys = svc.provider_keys(provider_id)
    pool_status = {}
    for entry in request.app.state.engine.provider_status():
        if entry["id"] == provider_id:
            pool_status = {s["key"]: s for s in entry.get("keys", [])}
    result = []
    for i, k in enumerate(keys):
        status = pool_status.get(k) if k in pool_status else None
        result.append({"index": i, "masked": _mask(k), "status": status})
    return {"success": True, "data": {"keys": result}}


@router.post("/providers/{provider_id}/keys")
async def add_key(provider_id: str, body: KeyBody, request: Request):
    svc = request.app.state.engine.config
    try:
        svc.add_provider_key(provider_id, body.key)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"success": True}


@router.delete("/providers/{provider_id}/keys/{index}")
async def remove_key(provider_id: str, index: int, request: Request):
    svc = request.app.state.engine.config
    try:
        svc.remove_provider_key(provider_id, index)
    except IndexError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"success": True}
```

- [ ] **Step 4: 实现 token_routes.py 并修改 auth.py**

`src/searchhub/api/admin/token_routes.py`:
```python
from __future__ import annotations

import hashlib
import secrets as _secrets
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from searchhub.api.admin.session import require_admin
from searchhub.config import TokenEntry

router = APIRouter(prefix="/api/admin", tags=["admin"],
                   dependencies=[Depends(require_admin)])


class TokenCreateBody(BaseModel):
    name: str = Field(min_length=1, max_length=64)


@router.get("/tokens")
async def list_tokens(request: Request):
    tokens = request.app.state.engine.config.get().auth.tokens
    return {"success": True, "data": {"tokens": [
        {"id": t.id, "name": t.name, "created_at": t.created_at,
         "revoked": t.revoked, "hash_prefix": t.token_hash[:8]}
        for t in tokens]}}


@router.post("/tokens")
async def create_token(body: TokenCreateBody, request: Request):
    svc = request.app.state.engine.config
    raw = _secrets.token_urlsafe(32)
    entry = TokenEntry(name=body.name,
                       token_hash=hashlib.sha256(raw.encode()).hexdigest(),
                       id=_secrets.token_hex(8), created_at=time.time())
    cfg = svc.get()
    cfg.auth.tokens.append(entry)
    svc.save_config(cfg)
    return {"success": True, "data": {"id": entry.id, "name": entry.name, "token": raw}}


@router.delete("/tokens/{token_id}")
async def delete_token(token_id: str, request: Request):
    svc = request.app.state.engine.config
    cfg = svc.get()
    new = [t for t in cfg.auth.tokens if t.id != token_id]
    if len(new) == len(cfg.auth.tokens):
        raise HTTPException(status_code=404, detail="token not found")
    cfg.auth.tokens = new
    svc.save_config(cfg)
    return {"success": True}
```

`src/searchhub/api/auth.py` 的 `_authorized` 修改：
```python
def _authorized(config: AppConfig, token: str) -> bool:
    digest = hashlib.sha256(token.encode()).hexdigest()
    return any(hmac.compare_digest(digest, t.token_hash) and not t.revoked
               for t in config.auth.tokens)
```

- [ ] **Step 5: 运行确认通过**

Run: `.venv/bin/pytest tests/api/admin/test_keys_tokens.py -v`
Expected: PASS（5 passed）

- [ ] **Step 6: 回归 + 提交**

Run: `.venv/bin/pytest -v`
Expected: 全绿

```bash
git add src/searchhub/api/admin/keys_routes.py src/searchhub/api/admin/token_routes.py \
        src/searchhub/api/auth.py tests/api/admin/test_keys_tokens.py
git commit -m "feat: admin key pool and caller-token management, revoked token support"
```

---

### Task 7: 管理路由——历史查询与统计

**Files:**
- Create: `src/searchhub/api/admin/stats_routes.py`
- Test: `tests/api/admin/test_stats_routes.py`

**Interfaces:**
- Consumes: `require_admin`、`engine.history`（RequestLogRepo）、`engine.provider_status()`
- Produces: `router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])`：
  - `GET /api/admin/history`，query 参数：`capability`、`provider`、`token`、`from_ts`、`to_ts`（float）、`q`、`limit`（默认100，上限500）、`offset`（>=0）→ `{"success": True, "data": {"rows": [<RequestLogRepo.query 行>]}}`
  - `GET /api/admin/stats/summary?hours=24` → `{"success": True, "data": {<summary(since)>..., "providers": <provider_status()>}}`
  - `GET /api/admin/stats/timeseries?hours=24` → `{"success": True, "data": {"rows": [timeseries 每小时]}}`

- [ ] **Step 1: 写失败测试**

`tests/api/admin/test_stats_routes.py`（完整内容，含 `caller_token` fixture——`/v1/search` 需要有效调用方 token 才会产生历史）:
```python
import time

import pytest


@pytest.fixture
def caller_token(admin_client):
    r = admin_client.post("/api/admin/tokens", json={"name": "test-agent"})
    return r.json()["data"]["token"]


def test_history_records_and_lists(admin_client, caller_token):
    headers = {"Authorization": f"Bearer {caller_token}"}
    r = admin_client.get("/api/admin/history")
    assert r.json()["data"]["rows"] == []
    admin_client.get("/v1/search", params={"q": "hello"}, headers=headers)
    rows = admin_client.get("/api/admin/history").json()["data"]["rows"]
    assert len(rows) == 1
    assert rows[0]["capability"] == "search"
    assert rows[0]["query"] == "hello"
    assert rows[0]["success"] == 0  # 无供应商
    assert rows[0]["token_name"] == "test-agent"


def test_history_filters_and_pagination(admin_client, caller_token):
    headers = {"Authorization": f"Bearer {caller_token}"}
    for i in range(5):
        admin_client.get("/v1/search", params={"q": f"q{i}"}, headers=headers)
    r = admin_client.get("/api/admin/history", params={"limit": 2})
    assert len(r.json()["data"]["rows"]) == 2
    r = admin_client.get("/api/admin/history", params={"limit": 2, "offset": 2})
    assert len(r.json()["data"]["rows"]) == 2
    r = admin_client.get("/api/admin/history", params={"q": "q3"})
    assert len(r.json()["data"]["rows"]) == 1
    r = admin_client.get("/api/admin/history", params={"capability": "extract"})
    assert r.json()["data"]["rows"] == []


def test_stats_summary_and_timeseries(admin_client, caller_token):
    headers = {"Authorization": f"Bearer {caller_token}"}
    for i in range(3):
        admin_client.get("/v1/search", params={"q": f"q{i}"}, headers=headers)
    r = admin_client.get("/api/admin/stats/summary")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["total"] == 3
    assert data["searches"] == 3
    assert data["extracts"] == 0
    assert data["success"] == 0
    assert data["success_rate"] == 0.0
    assert "providers" in data
    r = admin_client.get("/api/admin/stats/timeseries")
    rows = r.json()["data"]["rows"]
    assert len(rows) >= 1
    assert sum(x["count"] for x in rows) == 3
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/pytest tests/api/admin/test_stats_routes.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现**

`src/searchhub/api/admin/stats_routes.py`:
```python
from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Request

from searchhub.api.admin.session import require_admin

router = APIRouter(prefix="/api/admin", tags=["admin"],
                   dependencies=[Depends(require_admin)])


@router.get("/history")
async def list_history(request: Request, capability: str | None = None,
                       provider: str | None = None, token: str | None = None,
                       from_ts: float | None = None, to_ts: float | None = None,
                       q: str | None = None, limit: int = 100, offset: int = 0):
    rows = await request.app.state.engine.history.query(
        capability=capability, provider=provider, token=token,
        from_ts=from_ts, to_ts=to_ts, q=q,
        limit=min(limit, 500), offset=max(offset, 0))
    return {"success": True, "data": {"rows": rows}}


@router.get("/stats/summary")
async def stats_summary(request: Request, hours: float = 24):
    since = time.time() - hours * 3600
    data = await request.app.state.engine.history.summary(since)
    data["providers"] = request.app.state.engine.provider_status()
    return {"success": True, "data": data}


@router.get("/stats/timeseries")
async def stats_timeseries(request: Request, hours: int = 24):
    since = time.time() - hours * 3600
    rows = await request.app.state.engine.history.timeseries(since, 3600)
    return {"success": True, "data": {"rows": rows}}
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/pytest tests/api/admin/test_stats_routes.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: 提交**

```bash
git add src/searchhub/api/admin/stats_routes.py tests/api/admin/test_stats_routes.py
git commit -m "feat: admin history, stats summary and timeseries endpoints"
```

---

### Task 8: app 接线、后台清理任务与 README

**Files:**
- Modify: `src/searchhub/api/app.py`
- Modify: `README.md`
- Test: `tests/api/test_health.py`（不动）；新增 `tests/test_app_lifespan.py`

**Interfaces:**
- Consumes: `RequestLogRepo`、`SessionStore`、`config.session_secret()`、`ADMIN_PASSWORD` 环境变量
- Produces:
  - lifespan：`history = RequestLogRepo(data_dir / "history.db")`；`engine = SearchHubEngine(config, cache, http, history=history)`；首次启动密码：`cfg.admin.password_hash` 为空时 → `os.environ.get("ADMIN_PASSWORD") or "admin"`，无 env 时 `logger.warning` 提示默认密码，`config.set_admin_password(...)`；`session_store = SessionStore(config.session_secret())`；`app.state` 增加 `history`、`session_store`；后台任务 `asyncio.create_task(_cleanup_loop(...))`，shutdown 时 `cancel()`；关闭顺序：cancel task → http.aclose → cache.close → history.close
  - `async def _cleanup_loop(history: RequestLogRepo, cache: CacheRepo | None, config: ConfigService)`：每小时循环，`await history.purge_before(now - cfg.history.retention_days * 86400)` 与 `await cache.purge_expired()`，异常 `logger.exception`
  - 挂载：`session_router`（session.py，无 require_admin 依赖）+ `config_router`/`keys_router`/`token_router`/`stats_router`
  - `create_app` 顺序：admin 密码初始化必须先于 `engine.maybe_reload()`（避免注册表版本错位）
- README 追加：管理后台说明（`/api/admin/*` 登录、默认密码、`ADMIN_PASSWORD` 环境变量、改密、Token 创建）

- [ ] **Step 1: 写失败测试**

`tests/test_app_lifespan.py`:
```python
from fastapi.testclient import TestClient

from searchhub.api.app import create_app
from searchhub.config import ConfigService


def test_first_boot_uses_env_password(data_dir, monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "envpass123")
    with TestClient(create_app(data_dir)) as c:
        r = c.post("/api/admin/login",
                   json={"username": "admin", "password": "envpass123"})
        assert r.status_code == 200
    cs = ConfigService(data_dir)
    cs.load()
    assert cs.verify_admin_password("envpass123") is True


def test_first_boot_defaults_to_admin(data_dir, monkeypatch):
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    with TestClient(create_app(data_dir)) as c:
        r = c.post("/api/admin/login", json={"username": "admin", "password": "admin"})
        assert r.status_code == 200


def test_existing_password_not_overwritten(data_dir):
    cs = ConfigService(data_dir)
    cs.load()
    cs.set_admin_password("keepme123")
    with TestClient(create_app(data_dir)) as c:
        r = c.post("/api/admin/login", json={"username": "admin", "password": "keepme123"})
        assert r.status_code == 200
        r = c.post("/api/admin/login", json={"username": "admin", "password": "admin"})
        assert r.status_code == 401


def test_admin_routes_mounted(admin_client):
    assert admin_client.get("/api/admin/config").status_code == 200
    assert admin_client.get("/api/admin/tokens").status_code == 200
    assert admin_client.get("/api/admin/history").status_code == 200
    assert admin_client.get("/api/admin/stats/summary").status_code == 200
    assert admin_client.post("/api/admin/providers/nope/test").status_code == 404
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/pytest tests/test_app_lifespan.py -v`
Expected: FAIL（路由 404 / lifespan 未接线）

- [ ] **Step 3: 实现 app.py**

`src/searchhub/api/app.py` 整体替换：
```python
from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from searchhub import __version__
from searchhub.api.admin.config_routes import router as admin_config_router
from searchhub.api.admin.keys_routes import router as admin_keys_router
from searchhub.api.admin.session import SessionStore, router as admin_session_router
from searchhub.api.admin.stats_routes import router as admin_stats_router
from searchhub.api.admin.token_routes import router as admin_token_router
from searchhub.api.routes_extract import router as extract_router
from searchhub.api.routes_health import router as health_router
from searchhub.api.routes_providers import router as providers_router
from searchhub.api.routes_search import router as search_router
from searchhub.config import ConfigService
from searchhub.orchestrator import SearchHubEngine
from searchhub.storage.cache import CacheRepo
from searchhub.storage.history import RequestLogRepo

logger = logging.getLogger(__name__)


async def _cleanup_loop(history: RequestLogRepo, cache: CacheRepo | None,
                        config: ConfigService) -> None:
    while True:
        try:
            cfg = config.get()
            await history.purge_before(time.time() - cfg.history.retention_days * 86400)
            if cache is not None:
                await cache.purge_expired()
        except Exception:
            logger.exception("cleanup loop error")
        await asyncio.sleep(3600)


def create_app(data_dir: Path | None = None) -> FastAPI:
    data_dir = Path(data_dir) if data_dir else Path.cwd() / "data"

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        config = ConfigService(data_dir)
        config.load()
        cache = CacheRepo(data_dir / "cache.db")
        http = httpx.AsyncClient(timeout=60)
        history = RequestLogRepo(data_dir / "history.db")
        cfg = config.get()
        if not cfg.admin.password_hash:
            default = os.environ.get("ADMIN_PASSWORD") or "admin"
            if not os.environ.get("ADMIN_PASSWORD"):
                logger.warning("ADMIN_PASSWORD not set — using default password 'admin'. "
                               "Change it from the UI as soon as possible.")
            config.set_admin_password(default)
        engine = SearchHubEngine(config, cache, http, history=history)
        engine.maybe_reload()
        app.state.engine = engine
        app.state.http = http
        app.state.history = history
        app.state.data_dir = data_dir
        app.state.session_store = SessionStore(config.session_secret())
        cleanup_task = asyncio.create_task(_cleanup_loop(history, cache, config))
        yield
        cleanup_task.cancel()
        await http.aclose()
        await cache.close()
        await history.close()

    app = FastAPI(title="SearchHub", version=__version__, lifespan=lifespan)

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        return JSONResponse(status_code=exc.status_code,
                            content={"success": False, "error": exc.detail})

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        errors = exc.errors()
        first = errors[0] if errors else {}
        loc = ".".join(str(p) for p in first.get("loc", ()))
        msg = first.get("msg", "invalid request")
        summary = f"{loc}: {msg}" if loc else msg
        return JSONResponse(status_code=422,
                            content={"success": False, "error": f"validation error: {summary}"})

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled exception in %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500,
                            content={"success": False, "error": "internal error"})

    app.include_router(health_router)
    app.include_router(search_router)
    app.include_router(extract_router)
    app.include_router(providers_router)
    app.include_router(admin_session_router)
    app.include_router(admin_config_router)
    app.include_router(admin_keys_router)
    app.include_router(admin_token_router)
    app.include_router(admin_stats_router)
    return app
```

- [ ] **Step 4: README 追加管理后台章节**

`README.md` 末尾追加：
```markdown
## 管理后台（M2）

管理 API 位于 `/api/admin/*`（与公开 API 分离，使用独立管理员会话）：

- 登录：`POST /api/admin/login`（`{"username", "password"}`），会话存 httpOnly Cookie
- 首次启动：若 `config.yaml` 无密码哈希，使用环境变量 `ADMIN_PASSWORD`；未设置则默认 `admin/admin`（启动日志有警告，请尽快在 UI 改密）
- 功能：供应商 CRUD 与连接测试、Key 池增删（掩码显示）、策略/缓存/历史设置、调用方 Token 创建/吊销、历史查询、统计（summary + 每小时时序）、配置版本查看
- 所有写操作原子写入 `data/config.yaml`/`data/secrets.env` 并热重载，自动滚动备份 5 份
- 历史记录存 `data/history.db`，默认保留 30 天，后台每小时自动清理；`history.redact_queries: true` 可对 query 落盘前 sha1
```

- [ ] **Step 5: 运行确认通过**

Run: `.venv/bin/pytest tests/test_app_lifespan.py -v`
Expected: PASS（4 passed）

- [ ] **Step 6: 全量回归**

Run: `.venv/bin/pytest -v`
Expected: 全绿（88 + 7 + 6 + 6 + 6 + 8 + 5 + 3 + 4 中前序任务的测试均已并入）

- [ ] **Step 7: 提交**

```bash
git add src/searchhub/api/app.py README.md tests/test_app_lifespan.py
git commit -m "feat: wire admin API, cleanup task, first-boot admin password; docs"
```

---

## Self-Review

- **Spec 覆盖**（设计文档 §五）：管理员登录/登出/改密 → Task 3+8；供应商 CRUD + 连接测试 → Task 5；Key 池 UI 管理（掩码/状态）→ Task 6；策略/缓存/历史设置 → Task 5；调用方 token 创建/吊销 → Task 6；统计（24h 请求量/缓存命中率/成功率/延迟曲线）→ Task 7；历史查询（筛选/分页/脱敏/保留期）→ Task 4+7+8；配置版本显示 → Task 5；统一错误形状 → 沿用 M1 handler；密钥永不回显 → Task 5/6 掩码逻辑。
- **占位符扫描**：无 TBD/TODO；所有任务含完整测试与实现代码。
- **类型一致性**：`require_admin` 依赖名与路由使用一致；`engine.history` 属性在 stats_routes/app.py 中一致；`ConfigService.add/remove_provider_key` 异常类型与路由映射（ValueError→400、IndexError→404）一致；`SessionStore` 构造/方法签名一致；`_mask` 规则与 KeyPool 掩码规则一致。
- 已知取舍：登录无失败限速（M2B 或后续版本加）；`history` 查询对 `limit` 未做 0 保护（route 已 clamp offset>=0、limit<=500，limit<=0 返回空——可接受）；admin 路由未做 CSRF 防护（Cookie 为 SameSite=Lax，POST 跨站表单会带 cookie——`Content-Type: application/json` 触发 preflight 阻止简单跨站表单，风险可接受）。
