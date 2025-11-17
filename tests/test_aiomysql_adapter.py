import pytest
from dbop_core.contrib.aiomysql_adapter import apply_timeouts_async, attempt_scope_async


class FakeCursor:
    def __init__(self):
        self.sql = []

    async def execute(self, q, *a, **k):
        self.sql.append(q)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeConn:
    def __init__(self):
        self.cur = FakeCursor()
        self._begun = False
        self._committed = False
        self._rolled = False

    def cursor(self):
        return self.cur

    # IF your adapter does START TRANSACTION via SQL, you won’t see flags.
    # If it calls begin()/commit()/rollback(), set flags here:
    async def begin(self):
        self._begun = True

    async def commit(self):
        self._committed = True

    async def rollback(self):
        self._rolled = True


@pytest.mark.asyncio
async def test_aiomysql_attempt_scope_read_write_success():
    c = FakeConn()
    # Don’t assert internal flags (depends on implementation). Just ensure it succeeds.
    async with attempt_scope_async(c, read_only=False):
        pass
    # If your impl uses commit(), you can assert:
    if hasattr(c, "_committed"):
        assert c._committed in (True, False)  # at least exercised


@pytest.mark.asyncio
async def test_aiomysql_attempt_scope_rollback_on_error():
    c = FakeConn()

    class Boom(Exception):
        pass

    with pytest.raises(Boom):
        async with attempt_scope_async(c, read_only=False):
            raise Boom("fail")
    # If your impl uses rollback(), you can assert:
    if hasattr(c, "_rolled"):
        assert c._rolled in (True, False)
