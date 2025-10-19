from __future__ import annotations
from contextlib import asynccontextmanager, suppress


@asynccontextmanager
async def attempt_scope_async(conn, *, read_only: bool = False):
    """
    Hold an outer transaction for the attempt and nest a savepoint.
    This matches asyncpg's context-manager API and the fake used in unit tests.
    """
    async with conn.transaction():  # outer txn for the whole attempt
        if read_only:
            with suppress(Exception):
                await conn.execute("SET TRANSACTION READ ONLY")

        async with conn.transaction():  # inner txn == SAVEPOINT
            yield
        # success -> inner CM releases; outer CM commits when exiting


async def apply_timeouts_async(
    conn, *, lock_timeout_s: int | None, stmt_timeout_s: int | None
) -> None:
    """
    Best-effort per-attempt timeouts (run this *inside* a transaction).
    """
    if lock_timeout_s is not None:
        await conn.execute(f"SET LOCAL lock_timeout = '{int(lock_timeout_s)}s'")
    if stmt_timeout_s is not None:
        await conn.execute(f"SET LOCAL statement_timeout = '{int(stmt_timeout_s)}s'")
