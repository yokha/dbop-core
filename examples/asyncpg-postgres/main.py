from __future__ import annotations
import os
import asyncio
from dotenv import load_dotenv

from dbop_core.core import execute, RetryPolicy
from dbop_core.classify import dbapi_classifier
from dbop_core.contrib.asyncpg_adapter import attempt_scope_async, apply_timeouts_async
import asyncpg

load_dotenv()
DSN = os.getenv("POSTGRES_DSN", "postgresql://postgres:postgres@localhost:5432/dbop")

async def create_schema(conn: asyncpg.Connection) -> None:
    # Ensure UNIQUE so examples are consistent across psycopg/asyncpg runs
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS items(
            id   serial PRIMARY KEY,
            name text UNIQUE
        )
    """)
    await conn.execute("INSERT INTO items(name) VALUES ('alpha') ON CONFLICT (name) DO NOTHING")
    await conn.execute("INSERT INTO items(name) VALUES ('beta')  ON CONFLICT (name) DO NOTHING")

async def select_count(conn: asyncpg.Connection) -> int:
    row = await conn.fetchrow("SELECT COUNT(*) AS c FROM items")
    return int(row["c"])

async def insert_one(conn: asyncpg.Connection, name: str) -> None:
    await conn.execute(
        "INSERT INTO items(name) VALUES ($1) ON CONFLICT (name) DO NOTHING",
        name,
    )

async def main() -> None:
    policy = RetryPolicy(max_retries=5, initial_delay=0.05, max_delay=0.5)
    conn = await asyncpg.connect(DSN)
    try:
        await create_schema(conn)

        async def write():
            return await execute(
                lambda: insert_one(conn, "gamma"),
                classifier=dbapi_classifier,
                attempt_scope_async=lambda read_only=False: attempt_scope_async(conn, read_only=read_only),
                pre_attempt=lambda: apply_timeouts_async(conn, lock_timeout_s=3, stmt_timeout_s=10),
                policy=policy,
            )

        async def read():
            return await execute(
                lambda: select_count(conn),
                classifier=dbapi_classifier,
                attempt_scope_async=lambda read_only=False: attempt_scope_async(conn, read_only=True),
                pre_attempt=lambda: apply_timeouts_async(conn, lock_timeout_s=3, stmt_timeout_s=10),
                policy=policy,
                read_only=True,
            )

        await write()
        cnt = await read()
        print("Row count:", cnt)
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
