import pytest
from dbop_core.contrib.aiosqlite_adapter import attempt_scope_async


class ConnBoomOnRollback:
    def __init__(self):
        self.sql = []
        self.rollback_called = False
        self._first_savepoint_failed = False  # control first SAVEPOINT attempt

    async def execute(self, q):
        self.sql.append(q)
        # First SAVEPOINT attempt should fail -> triggers started_outer=True
        if q.startswith("SAVEPOINT dbop_runner") and not self._first_savepoint_failed:
            self._first_savepoint_failed = True
            raise RuntimeError("savepoint creation failed (first attempt)")
        # subsequent SAVEPOINT/BEGIN/ROLLBACK TO ... should succeed

    async def commit(self):
        pass

    async def rollback(self):
        self.rollback_called = True
        # make rollback itself fail so the adapter's suppress(Exception) is covered
        raise RuntimeError("outer rollback failed")


@pytest.mark.asyncio
async def test_aiosqlite_outer_rollback_is_suppressed():
    c = ConnBoomOnRollback()

    class Boom(Exception):
        pass

    with pytest.raises(Boom):
        async with attempt_scope_async(c, read_only=False):
            # trigger the exception path inside the scope
            raise Boom("trigger error")
    # Because first SAVEPOINT failed, started_outer was True -> rollback attempted (and suppressed)
    assert c.rollback_called is True
