from __future__ import annotations

from contextlib import asynccontextmanager, suppress
from typing import Optional


@asynccontextmanager
async def attempt_scope_async(conn, read_only: bool = False):
    """
    aiosqlite attempt scope. SQLite supports SAVEPOINT; we use it to
    keep parity with other backends and allow inner retries.
    """
    # Try SAVEPOINT directly; if that fails, start a txn then SAVEPOINT.
    started_outer = False
    try:
        try:
            await conn.execute("SAVEPOINT dbop_runner")
        except Exception:
            started_outer = True
            await conn.execute("BEGIN")
            # SQLite doesn't have per-txn READ ONLY we can set here
            await conn.execute("SAVEPOINT dbop_runner")

        try:
            yield
            with suppress(Exception):
                await conn.execute("RELEASE SAVEPOINT dbop_runner")
            if started_outer:
                await conn.commit()
        except Exception:
            with suppress(Exception):
                await conn.execute("ROLLBACK TO SAVEPOINT dbop_runner")
            if started_outer:
                with suppress(Exception):
                    await conn.rollback()
            raise
    finally:
        # aiosqlite keeps the connection open; nothing to close here
        pass


async def apply_timeouts_async(
    conn,
    lock_timeout_s: Optional[int] = None,
    stmt_timeout_s: Optional[int] = None,
) -> None:
    """
    SQLite only supports busy_timeout (connection-level) in ms.
    There is no server-side statement timeout.
    """
    if lock_timeout_s is not None:
        await conn.execute(f"PRAGMA busy_timeout = {int(lock_timeout_s) * 1000}")
    # stmt_timeout_s ignored
