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
