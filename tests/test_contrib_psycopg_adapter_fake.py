from __future__ import annotations
import types
import importlib
import sys
import pytest


def _install_fake_psycopg(monkeypatch):
    mod = types.ModuleType("psycopg")
    errors = types.ModuleType("psycopg.errors")

    class Error(Exception): ...

    errors.Error = Error
    mod.errors = errors

    class TxCM:
        def __init__(self, log):
            self.log = log

        def __enter__(self):
            self.log.append("enter-tx-sync")

        def __exit__(self, et, ev, tb):
            self.log.append("exit-tx-sync")

    class AsyncTxCM:
        def __init__(self, log):
            self.log = log

        async def __aenter__(self):
            self.log.append("enter-tx-async")

        async def __aexit__(self, et, ev, tb):
            self.log.append("exit-tx-async")

    class Cursor:
        def __init__(self, log):
            self.log = log

        def __enter__(self):
            return self

        def __exit__(self, et, ev, tb):
            pass

        def execute(self, sql):
            self.log.append(sql)

    class AsyncCursor:
        def __init__(self, log):
            self.log = log

        async def __aenter__(self):
            return self

        async def __aexit__(self, et, ev, tb):
            pass

        async def execute(self, sql):
            self.log.append(sql)

    class Connection:
        def __init__(self):
            self.log = []

        def transaction(self):
            return TxCM(self.log)

        def cursor(self):
            return Cursor(self.log)

    class AsyncConnection:
        def __init__(self):
            self.log = []

        def transaction(self):
            return AsyncTxCM(self.log)

        def cursor(self):
            return AsyncCursor(self.log)

    mod.Connection = Connection
    mod.AsyncConnection = AsyncConnection

    # Provide nested module path psycopg.async_.connection.AsyncConnection
    async_pkg = types.ModuleType("psycopg.async_")
    async_conn_mod = types.ModuleType("psycopg.async_.connection")
    async_conn_mod.AsyncConnection = AsyncConnection

    monkeypatch.setitem(sys.modules, "psycopg", mod)
    monkeypatch.setitem(sys.modules, "psycopg.errors", errors)
    monkeypatch.setitem(sys.modules, "psycopg.async_", async_pkg)
    monkeypatch.setitem(sys.modules, "psycopg.async_.connection", async_conn_mod)


@pytest.mark.usefixtures("monkeypatch")
def test_psycopg_sync_attempt_scope_and_timeouts(monkeypatch):
    _install_fake_psycopg(monkeypatch)
    # reload adapter to see fake module
    sa = importlib.import_module("dbop_core.contrib.psycopg_adapter")
    importlib.reload(sa)

    conn = sys.modules["psycopg"].Connection()  # type: ignore[attr-defined]

    # attempt scope (read-only)
    with sa.attempt_scope_sync(conn, read_only=True):
        pass
    log = conn.log
    # two nested transactions
    assert log.count("enter-tx-sync") == 2
    assert log.count("exit-tx-sync") == 2
    # read-only set
    assert any("SET TRANSACTION READ ONLY" in s for s in log)

    # per-attempt timeouts
    conn2 = sys.modules["psycopg"].Connection()  # type: ignore[attr-defined]
    sa.apply_timeouts_sync(conn2, lock_timeout_s=3, stmt_timeout_s=10)
    assert "SET LOCAL lock_timeout = '3s'" in "".join(conn2.log)
    assert "SET LOCAL statement_timeout = '10s'" in "".join(conn2.log)


@pytest.mark.asyncio
async def test_psycopg_async_attempt_scope_and_timeouts(monkeypatch):
    _install_fake_psycopg(monkeypatch)
    sa = importlib.import_module("dbop_core.contrib.psycopg_adapter")
    importlib.reload(sa)

    AsyncConnection = sys.modules["psycopg.async_.connection"].AsyncConnection  # type: ignore[attr-defined]
    conn = AsyncConnection()

    async with sa.attempt_scope_async(conn, read_only=True):
        pass
    log = conn.log
    assert log.count("enter-tx-async") == 2
    assert log.count("exit-tx-async") == 2
    assert any("SET TRANSACTION READ ONLY" in s for s in log)

    conn2 = AsyncConnection()
    await sa.apply_timeouts_async(conn2, lock_timeout_s=5, stmt_timeout_s=1)
    joined = "".join(conn2.log)
    assert "SET LOCAL lock_timeout = '5s'" in joined
    assert "SET LOCAL statement_timeout = '1s'" in joined
