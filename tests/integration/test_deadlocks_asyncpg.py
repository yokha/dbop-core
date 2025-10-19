from __future__ import annotations
import asyncio
import contextlib
import os
import pytest
import pytest_asyncio

try:
    import asyncpg
except Exception:  # pragma: no cover
    pytest.skip("asyncpg not installed; skipping asyncpg deadlock tests", allow_module_level=True)

from dbop_core.core import execute, RetryPolicy
from dbop_core.classify import dbapi_classifier
from dbop_core.contrib.asyncpg_adapter import attempt_scope_async, apply_timeouts_async

pytestmark = pytest.mark.integration

DSN = os.getenv("TEST_PG_DSN", "postgresql://postgres:postgres@127.0.0.1:55432/dbop")


@pytest_asyncio.fixture
async def pg_conn_pair():
    c1 = await asyncpg.connect(DSN)
    c2 = await asyncpg.connect(DSN)
    try:
        await c1.execute(
            """
            CREATE TABLE IF NOT EXISTS dlock (
                id integer PRIMARY KEY,
                v  integer NOT NULL
            )
        """
        )
        await c1.execute("INSERT INTO dlock(id, v) VALUES (1, 0) ON CONFLICT (id) DO NOTHING")
        await c1.execute("INSERT INTO dlock(id, v) VALUES (2, 0) ON CONFLICT (id) DO NOTHING")
        await c1.execute("UPDATE dlock SET v = 0 WHERE id IN (1, 2)")
        yield (c1, c2)
    finally:
        with contextlib.suppress(Exception):
            await c1.close()
        with contextlib.suppress(Exception):
            await c2.close()


@pytest.mark.asyncio
async def test_deadlock_is_retried_asyncpg(pg_conn_pair):
    """
    Force a deterministic transient lock error for t2 using NOWAIT:

      t1: BEGIN; lock row 1 (FOR UPDATE); wait; lock row 2; UPDATE both; COMMIT
      t2: attempt_scope-managed; lock row 2; wait; lock row 1 *NOWAIT* -> raises 55P03, runner retries

    On retry, t1 has committed, so t2 acquires both locks cleanly. We purposely
    make t2 a lock-only operation so only t1 updates => final (1,1).
    """
    c1, c2 = pg_conn_pair

    e_t1_locked = asyncio.Event()
    e_t2_locked = asyncio.Event()

    t2_attempts = 0

    async def t1():
        await c1.execute("BEGIN")
        try:
            # Lock row 1, signal t2, then go for row 2 (while t2 holds it)
            await c1.execute("SELECT 1 FROM dlock WHERE id = 1 FOR UPDATE")
            e_t1_locked.set()
            await e_t2_locked.wait()
            # small stagger so both are definitely holding their first lock
            await asyncio.sleep(0.05)
            await c1.execute("SELECT 1 FROM dlock WHERE id = 2 FOR UPDATE")
            # do the real work only here so final state is (1,1)
            await c1.execute("UPDATE dlock SET v = v + 1 WHERE id IN (1,2)")
            await c1.execute("COMMIT")
        except Exception:
            with contextlib.suppress(Exception):
                await c1.execute("ROLLBACK")
            raise

    # NOTE: attempt_scope_async manages the transaction/savepoint. Don't BEGIN/COMMIT here.
    async def t2_body():
        # Lock row 2 first, then try to grab row 1 with NOWAIT (will raise 55P03 while t1 holds row 1).
        await c2.execute("SELECT 1 FROM dlock WHERE id = 2 FOR UPDATE")
        e_t2_locked.set()
        await e_t1_locked.wait()
        await asyncio.sleep(0.05)
        # THIS is the deterministic transient: lock not available immediately.
        await c2.execute("SELECT 1 FROM dlock WHERE id = 1 FOR UPDATE NOWAIT")
        # Lock-only attempt; no UPDATE here on purpose so final (1,1).

    async def op():
        nonlocal t2_attempts
        t2_attempts += 1
        # set per-attempt timeouts inside txn so any waits don't hang forever
        await apply_timeouts_async(c2, lock_timeout_s=2, stmt_timeout_s=5)
        return await t2_body()

    async def run_t2():
        return await execute(
            lambda: op(),
            classifier=dbapi_classifier,  # sees asyncpg 55P03 (LockNotAvailableError) as transient
            attempt_scope_async=lambda read_only=False: attempt_scope_async(
                c2, read_only=read_only
            ),
            policy=RetryPolicy(max_retries=5, initial_delay=0.05, max_delay=0.2),
        )

    await asyncio.gather(t1(), run_t2())

    v1 = await c1.fetchval("SELECT v FROM dlock WHERE id = 1")
    v2 = await c1.fetchval("SELECT v FROM dlock WHERE id = 2")

    # Only t1 updates => deterministic final state
    assert (v1, v2) == (1, 1)
    # And we *did* retry on t2
    assert t2_attempts > 1, f"expected t2 to retry; attempts={t2_attempts}"
