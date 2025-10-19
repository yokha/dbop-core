from __future__ import annotations
import pytest

from dbop_core.contrib.dbapi_adapter import attempt_scope_sync, apply_timeouts_sync


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        pass

    def execute(self, sql: str):
        self.conn.queries.append(sql)
        if self.conn.fail_savepoint and sql.strip().upper().startswith("SAVEPOINT"):
            raise RuntimeError("savepoint unsupported")


class FakeConn:
    def __init__(self, fail_savepoint: bool = False):
        self.fail_savepoint = fail_savepoint
        self.queries: list[str] = []
        self.commit_count = 0
        self.rollback_count = 0

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commit_count += 1

    def rollback(self):
        self.rollback_count += 1


def test_dbapi_attempt_scope_savepoint_success():
    conn = FakeConn()
    with attempt_scope_sync(conn, read_only=True, backend="postgresql"):
        # inside scope do nothing
        pass
    q = " ".join(conn.queries)
    assert "BEGIN" in q and "SAVEPOINT" in q and "SET TRANSACTION READ ONLY" in q
    assert "RELEASE SAVEPOINT" in q
    assert conn.commit_count == 1
    assert conn.rollback_count == 0


def test_dbapi_attempt_scope_savepoint_exception_rolls_back():
    conn = FakeConn()
    with pytest.raises(RuntimeError):
        with attempt_scope_sync(conn, read_only=False, backend="postgresql"):
            raise RuntimeError("boom")
    q = " ".join(conn.queries)
    assert "SAVEPOINT" in q and "ROLLBACK TO SAVEPOINT" in q
    assert conn.commit_count == 0
    assert conn.rollback_count == 1


def test_dbapi_attempt_scope_fallback_when_no_savepoint():
    conn = FakeConn(fail_savepoint=True)
    with attempt_scope_sync(conn, read_only=True, backend="postgresql"):
        pass
    q = " ".join(conn.queries)
    # fallback path should NOT include SAVEPOINT
    assert "SAVEPOINT" not in q
    assert "BEGIN" in q
    assert "SET TRANSACTION READ ONLY" in q
    assert conn.commit_count == 1
    assert conn.rollback_count == 0


def test_dbapi_apply_timeouts_postgres():
    conn = FakeConn()
    apply_timeouts_sync(conn, backend="postgresql", lock_timeout_s=3, stmt_timeout_s=10)
    q = " ".join(conn.queries)
    assert "SET LOCAL lock_timeout = '3s'" in q
    assert "SET LOCAL statement_timeout = '10s'" in q


def test_dbapi_apply_timeouts_mysql():
    conn = FakeConn()
    apply_timeouts_sync(conn, backend="mysql", lock_timeout_s=7, stmt_timeout_s=2)
    q = " ".join(conn.queries)
    assert "SET SESSION innodb_lock_wait_timeout = 7" in q
    # MAX_EXECUTION_TIME in ms
    assert "SET SESSION MAX_EXECUTION_TIME = 2000" in q


def test_dbapi_apply_timeouts_sqlite_busy_timeout_only_for_lock():
    conn = FakeConn()
    apply_timeouts_sync(conn, backend="sqlite", lock_timeout_s=5, stmt_timeout_s=None)
    q = " ".join(conn.queries)
    assert "PRAGMA busy_timeout = 5000" in q
