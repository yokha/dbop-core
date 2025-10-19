from __future__ import annotations
from contextlib import contextmanager, suppress
from typing import Optional
import random
import string

# This adapter assumes a PEP 249 connection with .cursor(), .commit(), .rollback(),
# and optional feature flags used by tests/fakes:
#   - conn.supports_savepoint (default: True)
#   - conn.fail_savepoint     (default: False)


def _sp_name(prefix: str = "dbop") -> str:
    return prefix + "_" + "".join(random.choices(string.ascii_lowercase + string.digits, k=8))


@contextmanager
def attempt_scope_sync(conn, *, read_only: bool, backend: Optional[str] = None):
    """
    Generic DB-API transaction/savepoint scope.

    - Opens a transaction with BEGIN.
    - If SAVEPOINT is supported, creates one and releases it on success; otherwise
      just commits the transaction.
    - On error: rolls back to savepoint (if present) and then issues a full ROLLBACK
      to restore connection state.
    - read_only=True will best-effort set transaction read only for supported backends.

    NOTE: Exactly one `yield` (no fallthrough branches) to satisfy contextmanager protocol.
    """
    be = (backend or "").lower()
    sp_supported = getattr(conn, "supports_savepoint", True) and not getattr(
        conn, "fail_savepoint", False
    )

    sp: Optional[str] = None

    # Begin + (optional) read-only + (optional) savepoint — all BEFORE yield
    with conn.cursor() as cur:
        cur.execute("BEGIN")
        if read_only:
            with suppress(Exception):
                if be in ("postgresql", "mysql", "mariadb"):
                    cur.execute("SET TRANSACTION READ ONLY")
                # sqlite: no per-txn read-only toggle (ignore)

        if sp_supported:
            candidate = _sp_name()
            try:
                cur.execute(f"SAVEPOINT {candidate}")
                sp = candidate
            except Exception:
                # SAVEPOINT failed; continue without it
                sp = None

    try:
        # ---- user body runs here ----
        yield

        # Success path
        if sp:
            with suppress(Exception):
                with conn.cursor() as cur:
                    cur.execute(f"RELEASE SAVEPOINT {sp}")
        conn.commit()

    except Exception:
        # Error path
        if sp:
            with suppress(Exception):
                with conn.cursor() as cur:
                    cur.execute(f"ROLLBACK TO SAVEPOINT {sp}")
        with suppress(Exception):
            conn.rollback()
        raise


def apply_timeouts_sync(
    conn, *, backend: Optional[str], lock_timeout_s: Optional[int], stmt_timeout_s: Optional[int]
) -> None:
    """
    Best-effort per-attempt timeouts (no-ops where unsupported).
    """
    backend = (backend or "").lower()
    with conn.cursor() as cur:
        if backend == "postgresql":
            if lock_timeout_s is not None:
                cur.execute(f"SET LOCAL lock_timeout = '{int(lock_timeout_s)}s'")
            if stmt_timeout_s is not None:
                cur.execute(f"SET LOCAL statement_timeout = '{int(stmt_timeout_s)}s'")
        elif backend in ("mysql", "mariadb"):
            if lock_timeout_s is not None:
                cur.execute(f"SET SESSION innodb_lock_wait_timeout = {int(lock_timeout_s)}")
            if stmt_timeout_s is not None:
                # MAX_EXECUTION_TIME is in ms
                with suppress(Exception):
                    cur.execute(f"SET SESSION MAX_EXECUTION_TIME = {int(stmt_timeout_s) * 1000}")
        elif backend == "sqlite":
            # PRAGMA busy_timeout applies per-connection; changing it here is global. Use sparingly.
            if lock_timeout_s is not None:
                with suppress(Exception):
                    cur.execute(f"PRAGMA busy_timeout = {int(lock_timeout_s) * 1000}")
        else:
            # Unknown backend → no-op
            pass
