from __future__ import annotations

import os
import asyncio
from functools import partial
from pathlib import Path
from dotenv import load_dotenv
import aiomysql

from dbop_core.core import execute, RetryPolicy
from dbop_core.classify import dbapi_classifier
from dbop_core.contrib.aiomysql_adapter import attempt_scope_async, apply_timeouts_async

# Always load the examples/.env (next to the compose files)
ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(ENV_PATH, override=False)

MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "dbop")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "dbop")
# Prefer MYSQL_DB, then MYSQL_DATABASE; default to the compose-created DB name "dbop"
MYSQL_DB = os.getenv("MYSQL_DB") or os.getenv("MYSQL_DATABASE") or "dbop"


async def create_schema(conn) -> None:
    cur = await conn.cursor()
    try:
        await cur.execute(
            """
            CREATE TABLE IF NOT EXISTS items (
                id   INT PRIMARY KEY AUTO_INCREMENT,
                name VARCHAR(255) UNIQUE
            )
            """
        )
        await cur.execute("INSERT IGNORE INTO items(name) VALUES ('alpha'), ('beta')")
        await conn.commit()
    finally:
        await cur.close()


async def insert_one(conn, name: str) -> None:
    cur = await conn.cursor()
    try:
        # idempotent insert for repeated runs
        await cur.execute("INSERT IGNORE INTO items(name) VALUES (%s)", (name,))
    finally:
        await cur.close()


async def count_items(conn) -> int:
    cur = await conn.cursor()
    try:
        await cur.execute("SELECT COUNT(*) FROM items")
        (n,) = await cur.fetchone()
        return int(n)
    finally:
        await cur.close()


async def pre(conn) -> None:
    # per-attempt timeouts (best-effort; inside the attempt txn)
    await apply_timeouts_async(conn, lock_timeout_s=5, stmt_timeout_s=10)


async def main():
    conn = await aiomysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        db=MYSQL_DB,
        autocommit=False,
        charset="utf8mb4",
    )
    try:
        await create_schema(conn)
        policy = RetryPolicy(max_retries=5, initial_delay=0.05, max_delay=0.5)

        # write
        await execute(
            lambda: insert_one(conn, "gamma"),
            classifier=dbapi_classifier,
            attempt_scope_async=lambda read_only=False: attempt_scope_async(conn, read_only=read_only),
            pre_attempt=partial(pre, conn),
            policy=policy,
        )

        # read (read-only scope)
        total = await execute(
            lambda: count_items(conn),
            classifier=dbapi_classifier,
            attempt_scope_async=lambda read_only=False: attempt_scope_async(conn, read_only=True),
            pre_attempt=partial(pre, conn),
            policy=policy,
            read_only=True,
        )
        print("Row count:", total)
    finally:
        conn.close()  # aiomysql connection close is sync


if __name__ == "__main__":
    asyncio.run(main())
