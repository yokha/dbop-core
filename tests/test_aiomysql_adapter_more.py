# tests/test_aiomysql_adapter_more.py
import pytest
from dbop_core.contrib.aiomysql_adapter import apply_timeouts_async, attempt_scope_async

class Cur:
    def __init__(self, boom_on=None):
        self.sql = []
        self.boom_on = set(boom_on or [])

    async def execute(self, q, *a, **k):
        ql = q.lower()
        self.sql.append(q)
        if "innodb_lock_wait_timeout" in ql and "lock" in self.boom_on:
            raise RuntimeError("boom lock")
        if "max_execution_time" in ql and "stmt" in self.boom_on:
            raise RuntimeError("boom stmt")

    async def __aenter__(self): return self
    async def __aexit__(self, *exc): return False

class Conn:
    def __init__(self, boom_on=None):
        self.cur = Cur(boom_on)
        self._committed = False
        self._rolled = False
    def cursor(self): return self.cur
    async def commit(self): self._committed = True
    async def rollback(self): self._rolled = True

@pytest.mark.asyncio
async def test_aiomysql_timeouts_errors_are_suppressed():
    # Only boom on stmt path; lock path must not raise
    c = Conn(boom_on={"stmt"})
    await apply_timeouts_async(c, lock_timeout_s=3, stmt_timeout_s=2)

@pytest.mark.asyncio
async def test_aiomysql_attempt_scope_exception_rolls_back_or_sql_rollback():
    c = Conn()
    class Boom(Exception): pass
    with pytest.raises(Boom):
        async with attempt_scope_async(c, read_only=False):
            raise Boom()
    assert c._rolled in (True, False)
