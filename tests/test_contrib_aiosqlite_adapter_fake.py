from __future__ import annotations
import asyncio
import pytest
from dbop_core.contrib.aiosqlite_adapter import attempt_scope_async, apply_timeouts_async


class FakeConn:
    def __init__(self, fail_first_savepoint=True):
        self.queries = []
        self.fail_first_savepoint = fail_first_savepoint
        self.started = False

    async def execute(self, q):
        self.queries.append(q)
        if q.startswith("SAVEPOINT") and self.fail_first_savepoint:
            self.fail_first_savepoint = False
            raise RuntimeError("no transaction")
        if q == "BEGIN":
            self.started = True

    async def commit(self):
        self.queries.append("COMMIT")

    async def rollback(self):
        self.queries.append("ROLLBACK")


@pytest.mark.asyncio
async def test_aiosqlite_attempt_scope_uses_savepoint_and_commit():
    conn = FakeConn()
    async with attempt_scope_async(conn, read_only=True):
        conn.queries.append("-- body --")
    q = " ; ".join(conn.queries)
    assert (
        "BEGIN" in q
        and "SAVEPOINT dbop_runner" in q
        and "RELEASE SAVEPOINT dbop_runner" in q
        and "COMMIT" in q
    )


@pytest.mark.asyncio
async def test_aiosqlite_timeouts_busy_timeout():
    conn = FakeConn(fail_first_savepoint=False)
    await apply_timeouts_async(conn, lock_timeout_s=2, stmt_timeout_s=None)
    assert any(q.startswith("PRAGMA busy_timeout = 2000") for q in conn.queries)
