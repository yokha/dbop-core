from __future__ import annotations
import asyncio
import aiosqlite

from dbop_core.core import execute, RetryPolicy
from dbop_core.contrib.aiosqlite_adapter import attempt_scope_async, apply_timeouts_async


async def setup(conn):
    await conn.execute("CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT)")
    await conn.commit()


async def put(conn, k: str, v: str):
    await conn.execute("INSERT OR REPLACE INTO kv(k,v) VALUES (?,?)", (k, v))


async def get(conn, k: str) -> str | None:
    async with conn.execute("SELECT v FROM kv WHERE k=?", (k,)) as cur:
        row = await cur.fetchone()
        return row[0] if row else None


async def pre(conn) -> None:
    # per-attempt busy timeout in ms (connection-level)
    await apply_timeouts_async(conn, lock_timeout_s=3, stmt_timeout_s=None)


async def main():
    async with aiosqlite.connect("example.db") as conn:
        await setup(conn)
        policy = RetryPolicy(max_retries=3, initial_delay=0.05, max_delay=0.2, jitter=0.0)

        # write
        await execute(
            lambda: put(conn, "hello", "world"),
            attempt_scope_async=lambda read_only=False: attempt_scope_async(conn, read_only=read_only),
            pre_attempt=lambda: pre(conn),
            policy=policy,
        )

        # read (read-only)
        v = await execute(
            lambda: get(conn, "hello"),
            attempt_scope_async=lambda read_only=False: attempt_scope_async(conn, read_only=True),
            pre_attempt=lambda: pre(conn),
            policy=policy,
            read_only=True,
        )
        print("value:", v)


if __name__ == "__main__":
    asyncio.run(main())
