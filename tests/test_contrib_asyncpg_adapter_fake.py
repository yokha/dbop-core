from __future__ import annotations
import types
import importlib
import sys
import pytest


def _install_fake_asyncpg(monkeypatch):
    mod = types.ModuleType("asyncpg")

    class TxCM:
        def __init__(self, log):
            self.log = log

        async def __aenter__(self):
            self.log.append("enter-tx")
            return self

        async def __aexit__(self, et, ev, tb):
            self.log.append("exit-tx")

    class Connection:
        def __init__(self):
            self.log = []

        def transaction(self):
            return TxCM(self.log)

        async def execute(self, sql):
            self.log.append(sql)

    mod.Connection = Connection
    monkeypatch.setitem(sys.modules, "asyncpg", mod)


@pytest.mark.usefixtures("monkeypatch")
@pytest.mark.asyncio
async def test_asyncpg_attempt_scope_and_timeouts(monkeypatch):
    _install_fake_asyncpg(monkeypatch)
    apg = importlib.import_module("dbop_core.contrib.asyncpg_adapter")
    importlib.reload(apg)

    # create fake connection
    Connection = sys.modules["asyncpg"].Connection  # type: ignore[attr-defined]
    conn = Connection()

    # attempt scope (read-only)
    async with apg.attempt_scope_async(conn, read_only=True):
        pass
    log = conn.log
    # two nested transactions
    assert log.count("enter-tx") == 2
    assert log.count("exit-tx") == 2
    # read-only
    assert any("SET TRANSACTION READ ONLY" in s for s in log)

    # per-attempt timeouts
    conn2 = Connection()
    await apg.apply_timeouts_async(conn2, lock_timeout_s=2, stmt_timeout_s=7)
    joined = " ".join(conn2.log)
    assert "SET LOCAL lock_timeout = '2s'" in joined
    assert "SET LOCAL statement_timeout = '7s'" in joined
