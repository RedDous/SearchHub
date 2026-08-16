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
            """SELECT CAST(ROUND(ts / ?) AS INTEGER) * ? AS bucket, COUNT(*) AS total,
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
