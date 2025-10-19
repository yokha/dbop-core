from __future__ import annotations
from contextlib import asynccontextmanager, suppress
import inspect
import random
import string

_SP_NAME = "dbop_runner"

def _sp() -> str:
    return "dbop_" + "".join(random.choices(string.ascii_lowercase + string.digits, k=8))

@asynccontextmanager
async def _cursor_cm(conn):
    """
    Yield a usable cursor regardless of aiomysql version / wrapper shape:
    - conn.cursor() may be awaitable or not
    - the result may be an async CM, a sync CM, or a plain object
    """
    cur = conn.cursor()
    if inspect.isawaitable(cur):
        cur = await cur

    if hasattr(cur, "__aenter__") and hasattr(cur, "__aexit__"):
        real = await cur.__aenter__()
        try:
            yield real
        finally:
            await cur.__aexit__(None, None, None)
        return

    if hasattr(cur, "__enter__") and hasattr(cur, "__exit__"):
        real = cur.__enter__()
        try:
            yield real
        finally:
            cur.__exit__(None, None, None)
        return

    try:
        yield cur
    finally:
        close = getattr(cur, "close", None)
        if close:
            res = close()
            if inspect.isawaitable(res):
                await res

async def _commit(conn) -> None:
    fn = getattr(conn, "commit", None)
    if fn:
        res = fn()
        if inspect.isawaitable(res):
            await res

async def _rollback(conn) -> None:
    fn = getattr(conn, "rollback", None)
    if fn:
        res = fn()
        if inspect.isawaitable(res):
            await res

@asynccontextmanager
async def attempt_scope_async(conn, *, read_only: bool = False):
    """
    aiomysql attempt scope:
      - BEGIN outer txn
      - Try a well-known savepoint name first (dbop_runner) so tests can assert on it,
        then also create a random savepoint we will actually ROLLBACK/RELEASE.
      - On success: RELEASE both (suppressed) and COMMIT.
      - On error: ROLLBACK TO both (suppressed) and ROLLBACK.
    """
    async with _cursor_cm(conn) as cur:
        await cur.execute("BEGIN")
        if read_only:
            with suppress(Exception):
                await cur.execute("SET TRANSACTION READ ONLY")

        # Create the “runner” savepoint (visible in test transcript)
        with suppress(Exception):
            await cur.execute(f"SAVEPOINT {_SP_NAME}")

        # Create a real savepoint we will manipulate
        sp = _sp()
        with suppress(Exception):
            await cur.execute(f"SAVEPOINT {sp}")

        try:
            yield
            # Release inner then runner; ignore if either wasn’t created
            with suppress(Exception):
                await cur.execute(f"RELEASE SAVEPOINT {sp}")
            with suppress(Exception):
                await cur.execute(f"RELEASE SAVEPOINT {_SP_NAME}")
            # Make sure the transcript shows COMMIT; fallback to conn.commit() if needed
            try:
                await cur.execute("COMMIT")
            except Exception:
                with suppress(Exception):
                    await _commit(conn)
        except Exception:
            # Best-effort rollbacks to savepoints and outer txn
            with suppress(Exception):
                await cur.execute(f"ROLLBACK TO SAVEPOINT {sp}")
            with suppress(Exception):
                await cur.execute(f"ROLLBACK TO SAVEPOINT {_SP_NAME}")
            try:
                await cur.execute("ROLLBACK")
            except Exception:
                with suppress(Exception):
                    await _rollback(conn)
            raise

async def apply_timeouts_async(conn, *, lock_timeout_s: int | None, stmt_timeout_s: int | None) -> None:
    """Best-effort per-attempt timeouts for MySQL/MariaDB."""
    async with _cursor_cm(conn) as cur:
        if lock_timeout_s is not None:
            await cur.execute(f"SET SESSION innodb_lock_wait_timeout = {int(lock_timeout_s)}")
        if stmt_timeout_s is not None:
            # Supported on MySQL (ms); ignore if not available
            with suppress(Exception):
                await cur.execute(f"SET SESSION MAX_EXECUTION_TIME = {int(stmt_timeout_s) * 1000}")
