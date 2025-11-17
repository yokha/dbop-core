from __future__ import annotations

import os
import threading
import contextlib
import time
import pytest

try:
    import pymysql
except Exception:  # pragma: no cover
    pytest.skip("PyMySQL not installed; skipping MySQL deadlock tests", allow_module_level=True)

from dbop_core.core import execute, RetryPolicy
from dbop_core.classify import dbapi_classifier
from dbop_core.contrib.dbapi_adapter import attempt_scope_sync, apply_timeouts_sync

pytestmark = pytest.mark.integration

# Env provided by Makefile (docker compose); safe fallbacks for local runs
MYSQL_HOST = os.getenv("TEST_MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.getenv("TEST_MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("TEST_MYSQL_USER", "dbop")
MYSQL_PASSWORD = os.getenv("TEST_MYSQL_PASSWORD", "dbop")
MYSQL_DB = os.getenv("TEST_MYSQL_DB", "dbop")


def _connect():
    return pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DB,
        autocommit=False,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.Cursor,
    )


@pytest.fixture
def mysql_conn_pair():
    c1 = _connect()
    c2 = _connect()
    try:
        with c1.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS dlock (
                  id INT PRIMARY KEY,
                  v  INT NOT NULL
                ) ENGINE=InnoDB
                """
            )
            cur.execute("INSERT IGNORE INTO dlock(id,v) VALUES (1,0),(2,0)")
            # Reset baseline
            cur.execute("UPDATE dlock SET v = 0 WHERE id IN (1,2)")
        c1.commit()
        yield (c1, c2)
    finally:
        with contextlib.suppress(Exception):
            c1.close()
        with contextlib.suppress(Exception):
            c2.close()


def _is_deadlock_or_lockwait(e: BaseException) -> bool:
    msg = str(e).lower()
    # MySQL ER_LOCK_DEADLOCK=1213, ER_LOCK_WAIT_TIMEOUT=1205
    return "1213" in msg or "1205" in msg or "deadlock" in msg or "lock wait timeout" in msg


def test_deadlock_is_retried_pymysql(mysql_conn_pair):
    """
    Deterministic two-row deadlock:

      t1 (plain txn):
        - SELECT ... FOR UPDATE id=1
        - barrier
        - UPDATE id=2 (blocked by t2) -> deadlock victim likely
        - if deadlock: ROLLBACK; else COMMIT

      t2 (wrapped in dbop_core.execute, retried on deadlock):
        - attempt_scope_sync opens txn+savepoint
        - SELECT ... FOR UPDATE id=2
        - barrier
        - UPDATE id=1 then id=2
        - commit (runner handles retries)

    Final state from baseline (0,0) should be (1,1).
    """
    c1, c2 = mysql_conn_pair
    barrier = threading.Barrier(2, timeout=5.0)

    def t1():
        with c1.cursor() as cur:
            cur.execute("BEGIN")
            try:
                # Lock row 1 first
                cur.execute("SELECT id FROM dlock WHERE id=1 FOR UPDATE")
                barrier.wait()
                # Now try to touch row 2 (locked by t2) -> circular wait
                cur.execute("UPDATE dlock SET v = v + 1 WHERE id = 2")
                cur.execute("UPDATE dlock SET v = v + 1 WHERE id = 1")
                c1.commit()
            except BaseException as e:
                if _is_deadlock_or_lockwait(e):
                    with contextlib.suppress(Exception):
                        c1.rollback()
                else:
                    raise

    async def pre():
        # Best-effort per-attempt timeouts
        apply_timeouts_sync(c2, backend="mysql", lock_timeout_s=2, stmt_timeout_s=5)

    # Body for a single attempt (txn/savepoint owned by attempt_scope_sync)
    def t2_body():
        with c2.cursor() as cur:
            # Lock the *other* row first to create the cycle
            cur.execute("SELECT id FROM dlock WHERE id=2 FOR UPDATE")
            barrier.wait()
            # Then touch both rows in a deterministic order
            cur.execute("UPDATE dlock SET v = v + 1 WHERE id = 1")
            cur.execute("UPDATE dlock SET v = v + 1 WHERE id = 2")

    async def run_t2():
        return await execute(
            lambda: t2_body(),
            classifier=dbapi_classifier,
            attempt_scope=lambda read_only=False: attempt_scope_sync(
                c2, read_only=read_only, backend="mysql"
            ),
            pre_attempt=pre,
            policy=RetryPolicy(max_retries=5, initial_delay=0.05, max_delay=0.2),
        )

    # Launch workers: t1 is plain thread; t2 runs the async runner in its own loop/thread
    t1_exc: list[BaseException] = []
    t2_exc: list[BaseException] = []

    def t1_worker():
        try:
            t1()
        except BaseException as e:
            t1_exc.append(e)

    def t2_worker():
        import asyncio

        try:
            asyncio.run(run_t2())
        except BaseException as e:
            t2_exc.append(e)

    th1 = threading.Thread(target=t1_worker, daemon=True)
    th2 = threading.Thread(target=t2_worker, daemon=True)
    th1.start()
    th2.start()
    th1.join()
    th2.join()

    # Fail the test if background workers errored
    assert not t1_exc, f"t1 worker raised: {t1_exc[0]!r}"
    assert not t2_exc, f"t2 worker raised: {t2_exc[0]!r}"

    # Verify: exactly one txn succeeded -> both rows incremented once
    with c1.cursor() as cur:
        cur.execute("SELECT v FROM dlock WHERE id = 1")
        v1 = cur.fetchone()[0]
        cur.execute("SELECT v FROM dlock WHERE id = 2")
        v2 = cur.fetchone()[0]
    assert (v1, v2) == (1, 1)
