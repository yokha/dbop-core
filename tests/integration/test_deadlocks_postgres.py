from __future__ import annotations

import asyncio
import contextlib
import os
import pytest
import pytest_asyncio

# Skip cleanly if psycopg isn't available
try:
    import psycopg
    from psycopg import AsyncConnection
except Exception:  # pragma: no cover
    pytest.skip("psycopg not installed; skipping Postgres deadlock tests", allow_module_level=True)

from dbop_core.core import execute, RetryPolicy
from dbop_core.classify import dbapi_classifier
from dbop_core.contrib.psycopg_adapter import attempt_scope_async, apply_timeouts_async

pytestmark = pytest.mark.integration

DSN = os.getenv("TEST_PG_DSN", "postgresql://postgres:postgres@127.0.0.1:55432/dbop")


@pytest_asyncio.fixture
async def pg_conn_pair():
    """
    Provide two independent connections and a fresh 'dlock' table with rows (1,0) and (2,0).
    """
    c1 = await AsyncConnection.connect(DSN)
    c2 = await AsyncConnection.connect(DSN)
    try:
        async with c1.cursor() as cur:
            await cur.execute(
                """
                CREATE TABLE IF NOT EXISTS dlock (
                    id integer PRIMARY KEY,
                    v  integer NOT NULL
                )
                """
            )
            await cur.execute("INSERT INTO dlock(id, v) VALUES (1, 0) ON CONFLICT (id) DO NOTHING")
            await cur.execute("INSERT INTO dlock(id, v) VALUES (2, 0) ON CONFLICT (id) DO NOTHING")
            # Reset to baseline for this test run
            await cur.execute("UPDATE dlock SET v = 0 WHERE id IN (1, 2)")
            await c1.commit()
        yield (c1, c2)
    finally:
        with contextlib.suppress(Exception):
            await c1.close()
        with contextlib.suppress(Exception):
            await c2.close()


@pytest.mark.asyncio
async def test_deadlock_is_retried_psycopg(pg_conn_pair):
    """
    Induce a classic two-row update deadlock between two connections.
    - t1 runs on c1 and may deadlock; we EXPECT it to be the victim and roll back.
    - t2 runs on c2 but is wrapped by dbop_core.execute(...) so it will retry and succeed.
    Final state should reflect only one successful transaction: both rows incremented once.
    """
    c1, c2 = pg_conn_pair

    async def t1():
        async with c1.cursor() as cur:
            await cur.execute("BEGIN")
            try:
                await cur.execute("UPDATE dlock SET v = v + 1 WHERE id = 1")
                await asyncio.sleep(0.05)  # interleave
                await cur.execute("UPDATE dlock SET v = v + 1 WHERE id = 2")
                await c1.commit()
            except psycopg.errors.DeadlockDetected:
                # Expected victim: clean up connection state so the test can proceed
                await c1.rollback()

    async def t2_body():
        async with c2.cursor() as cur:
            await cur.execute("BEGIN")
            await cur.execute("UPDATE dlock SET v = v + 1 WHERE id = 2")
            await asyncio.sleep(0.05)  # interleave
            await cur.execute("UPDATE dlock SET v = v + 1 WHERE id = 1")
            await c2.commit()

    async def pre():
        # Per-attempt timeouts on the c2 connection
        await apply_timeouts_async(c2, lock_timeout_s=2, stmt_timeout_s=5)

    async def run_t2():
        return await execute(
            lambda: t2_body(),
            classifier=dbapi_classifier,
            attempt_scope_async=lambda read_only=False: attempt_scope_async(
                c2, read_only=read_only
            ),
            pre_attempt=pre,
            policy=RetryPolicy(max_retries=5, initial_delay=0.05, max_delay=0.2),
        )

    # Race them: t1 may deadlock & rollback; t2 should retry and eventually commit.
    await asyncio.gather(t1(), run_t2())

    # Verify final state: a single successful tx incremented both rows to 1.
    async with c1.cursor() as cur:
        await cur.execute("SELECT v FROM dlock WHERE id = 1")
        v1 = (await cur.fetchone())[0]
        await cur.execute("SELECT v FROM dlock WHERE id = 2")
        v2 = (await cur.fetchone())[0]
    assert (v1, v2) == (1, 1)
