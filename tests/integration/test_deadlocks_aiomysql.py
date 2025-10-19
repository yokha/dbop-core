from __future__ import annotations

import asyncio
import contextlib
import os
import pytest
import pytest_asyncio

# Skip cleanly if aiomysql isn't available
try:
    import aiomysql
except Exception:  # pragma: no cover
    pytest.skip(
        "aiomysql not installed; skipping MySQL async deadlock tests", allow_module_level=True
    )

from dbop_core.core import execute, RetryPolicy
from dbop_core.classify import dbapi_classifier
from dbop_core.contrib.aiomysql_adapter import attempt_scope_async, apply_timeouts_async

pytestmark = pytest.mark.integration

MYSQL_HOST = os.getenv("TEST_MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.getenv("TEST_MYSQL_PORT", "53306"))
MYSQL_USER = os.getenv("TEST_MYSQL_USER", "dbop")
MYSQL_PASSWORD = os.getenv("TEST_MYSQL_PASSWORD", "dbop")
MYSQL_DB = os.getenv("TEST_MYSQL_DB", "dbop")


@pytest_asyncio.fixture
async def mysql_conn_pair():
    """
    Provide two independent aiomysql connections and a fresh 'dlock' table with rows (1,0) and (2,0).
    """
    c1 = await aiomysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        db=MYSQL_DB,
        autocommit=False,
        charset="utf8mb4",
    )
    c2 = await aiomysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        db=MYSQL_DB,
        autocommit=False,
        charset="utf8mb4",
    )
    try:
        async with c1.cursor() as cur:
            await cur.execute(
                """
                CREATE TABLE IF NOT EXISTS dlock (
                    id INT PRIMARY KEY,
                    v  INT NOT NULL
                ) ENGINE=InnoDB
                """
            )
            await cur.execute("INSERT IGNORE INTO dlock(id, v) VALUES (1, 0), (2, 0)")
            await cur.execute("UPDATE dlock SET v = 0 WHERE id IN (1, 2)")
        await c1.commit()
        yield (c1, c2)
    finally:
        with contextlib.suppress(Exception):
            c1.close()
            await c1.wait_closed()
        with contextlib.suppress(Exception):
            c2.close()
            await c2.wait_closed()


@pytest.mark.asyncio
async def test_deadlock_is_retried_aiomysql(mysql_conn_pair):
    """
    Force a real InnoDB deadlock by updating rows in opposite order:

      t1 (c1): BEGIN; UPDATE id=1; wait; UPDATE id=2 -> may be victim; rollback.
      t2 (c2): attempt_scope-managed txn; UPDATE id=2; wait; UPDATE id=1 -> if victim, execute(...) retries.

    Final table state: both rows incremented equally; either once (victim=t1) or twice (victim=t2 with retry).
    """
    c1, c2 = mysql_conn_pair

    e_t1_locked = asyncio.Event()
    e_t2_locked = asyncio.Event()
    t1_deadlocked = False
    t2_attempts = 0

    async def t1():
        nonlocal t1_deadlocked
        async with c1.cursor() as cur:
            await cur.execute("BEGIN")
            try:
                await cur.execute("UPDATE dlock SET v = v + 1 WHERE id = 1")
                e_t1_locked.set()
                await e_t2_locked.wait()
                await asyncio.sleep(0.05)
                await cur.execute("UPDATE dlock SET v = v + 1 WHERE id = 2")
                await c1.commit()
            except Exception as e:
                # Expect either 1213 (deadlock) or 1205 (lock wait timeout)
                if "deadlock" in str(e).lower() or "lock wait timeout" in str(e).lower():
                    t1_deadlocked = True
                    with contextlib.suppress(Exception):
                        await c1.rollback()
                else:
                    raise

    # Body executed inside attempt_scope_async; do NOT BEGIN/COMMIT here.
    async def t2_body():
        async with c2.cursor() as cur:
            await cur.execute("UPDATE dlock SET v = v + 1 WHERE id = 2")
            e_t2_locked.set()
            await e_t1_locked.wait()
            await asyncio.sleep(0.05)
            await cur.execute("UPDATE dlock SET v = v + 1 WHERE id = 1")

    async def op():
        nonlocal t2_attempts
        t2_attempts += 1
        # Per-attempt timeouts
        await apply_timeouts_async(c2, lock_timeout_s=2, stmt_timeout_s=5)
        return await t2_body()

    async def run_t2():
        return await execute(
            lambda: op(),
            classifier=dbapi_classifier,  # classifies 1213/1205/etc. as transient
            attempt_scope_async=lambda read_only=False: attempt_scope_async(
                c2, read_only=read_only
            ),
            policy=RetryPolicy(max_retries=5, initial_delay=0.05, max_delay=0.2),
        )

    await asyncio.gather(t1(), run_t2())

    async with c1.cursor() as cur:
        await cur.execute("SELECT v FROM dlock WHERE id = 1")
        v1 = (await cur.fetchone())[0]
        await cur.execute("SELECT v FROM dlock WHERE id = 2")
        v2 = (await cur.fetchone())[0]

    # One side is the victim: both rows changed equally; either once (t1 victim) or twice (t2 victim -> retried)
    assert v1 == v2 and v1 in (1, 2)
    # And we actually exercised a deadlock path
    assert (
        t1_deadlocked or t2_attempts > 1
    ), f"Expected t1 deadlock or t2 retry; got t1_deadlocked={t1_deadlocked}, t2_attempts={t2_attempts}"
