import pytest
from dbop_core.contrib.dbapi_adapter import apply_timeouts_sync, attempt_scope_sync

class FakeCursor:
    def __init__(self, store): self.store = store
    def execute(self, q): self.store.append(q)
    def __enter__(self): return self
    def __exit__(self, exc_type, exc, tb): return False

class FakeConn:
    def __init__(self): self.store = []
    def cursor(self): return FakeCursor(self.store)
    # needed by attempt_scope_sync
    def commit(self): self.store.append("-- COMMIT")
    def rollback(self): self.store.append("-- ROLLBACK")

def test_dbapi_sqlite_timeouts_and_scope():
    c = FakeConn()
    apply_timeouts_sync(c, backend="sqlite", lock_timeout_s=3, stmt_timeout_s=None)
    with attempt_scope_sync(c, read_only=False):
        with c.cursor() as cur:
            cur.execute("SELECT 1")
    # optional: ensure no crash; sqlite busy_timeout may be connection-level only

def test_dbapi_postgres_timeouts():
    c = FakeConn()
    # Should not raise, even if it only applies inside a txn (no SQL captured here)
    apply_timeouts_sync(c, backend="postgresql", lock_timeout_s=3, stmt_timeout_s=10)
    assert True

def test_dbapi_mysql_timeouts():
    c = FakeConn()
    apply_timeouts_sync(c, backend="mysql", lock_timeout_s=5, stmt_timeout_s=1.2)
    joined = ";".join(c.store).lower()
    assert "innodb_lock_wait_timeout" in joined
    assert "max_execution_time" in joined

def test_dbapi_unknown_backend_graceful():
    c = FakeConn()
    apply_timeouts_sync(c, backend="weird", lock_timeout_s=None, stmt_timeout_s=None)
    assert c.store == []


class Cur:
    def __init__(self, log): self.log = log
    def execute(self, q):
        self.log.append(q)
        if q.startswith("RELEASE SAVEPOINT"):
            raise RuntimeError("release failed")
    def __enter__(self): return self
    def __exit__(self, *exc): return False

class Conn:
    supports_savepoint = True
    def __init__(self): self.log = []
    def cursor(self): return Cur(self.log)
    def commit(self): self.log.append("-- COMMIT")
    def rollback(self): self.log.append("-- ROLLBACK")

def test_release_savepoint_failure_is_suppressed_and_commit_happens():
    c = Conn()
    with attempt_scope_sync(c, read_only=False, backend="postgresql"):
        pass
    assert "-- COMMIT" in c.log
