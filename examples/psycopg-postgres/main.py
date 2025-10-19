from __future__ import annotations
import os
import asyncio
from functools import partial
from dotenv import load_dotenv

from dbop_core.core import execute, RetryPolicy
from dbop_core.classify import dbapi_classifier
from dbop_core.contrib.psycopg_adapter import attempt_scope_sync, apply_timeouts_sync
import psycopg

load_dotenv()  # reads examples/.env
DSN = os.getenv("POSTGRES_DSN", "postgresql://postgres:postgres@localhost:5432/dbop")


def create_schema(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        # make 'name' UNIQUE so ON CONFLICT works predictably
        cur.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id   serial PRIMARY KEY,
                name text UNIQUE
            )
        """)
        # seed a couple rows, ignore duplicates on reruns
        cur.execute("INSERT INTO items(name) VALUES ('alpha') ON CONFLICT (name) DO NOTHING")
        cur.execute("INSERT INTO items(name) VALUES ('beta')  ON CONFLICT (name) DO NOTHING")
    conn.commit()


def insert_one(conn: psycopg.Connection, name: str) -> None:
    with conn.cursor() as cur:
        cur.execute("INSERT INTO items(name) VALUES (%s) ON CONFLICT (name) DO NOTHING", (name,))


def select_count(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM items")
        (n,) = cur.fetchone()
        return int(n)


async def pre(conn: psycopg.Connection) -> None:
    """
    Async pre-attempt hook: apply per-attempt timeouts for Postgres.
    (Calls a sync helper; that's fine—this function just needs to be awaitable.)
    """
    apply_timeouts_sync(conn, lock_timeout_s=3, stmt_timeout_s=10)


async def main() -> None:
    policy = RetryPolicy(max_retries=5, initial_delay=0.05, max_delay=0.5)

    with psycopg.connect(DSN) as conn:
        create_schema(conn)

        # Write (with retries, nested SAVEPOINT via attempt_scope_sync)
        await execute(
            lambda: insert_one(conn, "gamma"),
            classifier=dbapi_classifier,
            attempt_scope=lambda read_only=False: attempt_scope_sync(conn, read_only=read_only),
            pre_attempt=partial(pre, conn),   # async pre_attempt ✅
            policy=policy,
        )

        # Read (read-only scope)
        count = await execute(
            lambda: select_count(conn),
            classifier=dbapi_classifier,
            attempt_scope=lambda read_only=False: attempt_scope_sync(conn, read_only=True),
            pre_attempt=partial(pre, conn),
            policy=policy,
            read_only=True,
        )

        print("Row count:", count)


if __name__ == "__main__":
    asyncio.run(main())
