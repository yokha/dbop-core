from __future__ import annotations
import os
import time
import asyncio
from functools import partial
from dotenv import load_dotenv
import pymysql
from pymysql.err import OperationalError

from dbop_core.core import execute, RetryPolicy
from dbop_core.classify import dbapi_classifier
from dbop_core.contrib.dbapi_adapter import attempt_scope_sync, apply_timeouts_sync

load_dotenv()

MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "dbop")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "dbop")
MYSQL_DB = os.getenv("MYSQL_DB", "dbop")


def connect(retries: int = 60, delay: float = 0.5, backoff: float = 1.25):
    """
    Try to connect with simple backoff so the example doesn't race the container boot.
    Tip: set MYSQL_HOST=127.0.0.1 if 'localhost' is flaky on your OS.
    """
    last_exc: Exception | None = None
    host = MYSQL_HOST
    # 'localhost' can resolve to ::1 on some systems; prefer IPv4 if desired:
    # host = "127.0.0.1" if MYSQL_HOST == "localhost" else MYSQL_HOST

    for _ in range(retries):
        try:
            return pymysql.connect(
                host=host,
                port=MYSQL_PORT,
                user=MYSQL_USER,
                password=MYSQL_PASSWORD,
                database=MYSQL_DB,
                autocommit=False,
                charset="utf8mb4",
                connect_timeout=3,
                read_timeout=10,
                write_timeout=10,
                cursorclass=pymysql.cursors.Cursor,
            )
        except (OperationalError, OSError) as e:
            last_exc = e
            time.sleep(delay)
            delay *= backoff
    raise RuntimeError("Could not connect to MySQL after retries") from last_exc


def create_schema(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id   INT PRIMARY KEY AUTO_INCREMENT,
                name VARCHAR(255) UNIQUE
            )
        """)
        # idempotent seeds
        cur.execute("INSERT IGNORE INTO items(name) VALUES ('alpha'), ('beta')")
    conn.commit()


def insert_one(conn, name: str) -> None:
    with conn.cursor() as cur:
        # idempotent insert so re-runs don't fail
        cur.execute("INSERT IGNORE INTO items(name) VALUES (%s)", (name,))


def count_items(conn) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM items")
        (n,) = cur.fetchone()
        return int(n)


async def pre(conn) -> None:
    """Async pre-attempt hook: call the sync timeout setter, but as an awaitable."""
    apply_timeouts_sync(conn, backend="mysql", lock_timeout_s=5, stmt_timeout_s=3)


async def main():
    policy = RetryPolicy(max_retries=5, initial_delay=0.05, max_delay=0.5)
    conn = connect()
    try:
        create_schema(conn)

        # write (with retries, savepoint, per-attempt timeouts)
        await execute(
            lambda: insert_one(conn, "gamma"),
            classifier=dbapi_classifier,
            attempt_scope=lambda read_only=False: attempt_scope_sync(
                conn, read_only=read_only, backend="mysql"
            ),
            pre_attempt=partial(pre, conn),  # async pre_attempt
            policy=policy,
        )

        # read (read-only scope)
        total = await execute(
            lambda: count_items(conn),
            classifier=dbapi_classifier,
            attempt_scope=lambda read_only=False: attempt_scope_sync(
                conn, read_only=True, backend="mysql"
            ),
            pre_attempt=partial(pre, conn),
            policy=policy,
            read_only=True,
        )

        print("Row count:", total)
    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())
