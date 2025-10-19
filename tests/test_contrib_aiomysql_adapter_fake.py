from __future__ import annotations
import asyncio
import pytest
from dbop_core.contrib.aiomysql_adapter import attempt_scope_async, apply_timeouts_async


class FakeCur:
    def __init__(self, conn):
        self.conn = conn

    async def execute(self, q):
        self.conn.queries.append(q)
        # First SAVEPOINT fails to force fallback
        if q.startswith("SAVEPOINT") and self.conn.fail_first_savepoint:
            self.conn.fail_first_savepoint = False
            raise RuntimeError("SAVEPOINT does not exist")
        if q == "BEGIN":
            self.conn.in_tx = True
        if q == "ROLLBACK":
            self.conn.in_tx = False

    async def close(self):
        pass


class FakeConn:
    def __init__(self, fail_first_savepoint=True):
        self.in_tx = False
        self.fail_first_savepoint = fail_first_savepoint
        self.queries = []

    async def cursor(self):
        return FakeCur(self)


@pytest.mark.asyncio
async def test_aiomysql_attempt_scope_fallback_then_commit():
    conn = FakeConn()
    async with attempt_scope_async(conn, read_only=True):
        conn.queries.append("-- body --")
    q = " ; ".join(conn.queries)
    # we should see fallback: BEGIN then SAVEPOINT, then RELEASE, COMMIT
    assert (
        "BEGIN" in q
        and "SAVEPOINT dbop_runner" in q
        and "RELEASE SAVEPOINT dbop_runner" in q
        and "COMMIT" in q
    )


@pytest.mark.asyncio
async def test_aiomysql_timeouts_best_effort():
    conn = FakeConn(fail_first_savepoint=False)
    await apply_timeouts_async(conn, lock_timeout_s=3, stmt_timeout_s=10)
    q = " ; ".join(conn.queries)
    assert "innodb_lock_wait_timeout = 3" in q
    # One (or both) of these is fine depending on flavor
    assert ("MAX_EXECUTION_TIME = 10000" in q) or ("max_statement_time = 10" in q)
