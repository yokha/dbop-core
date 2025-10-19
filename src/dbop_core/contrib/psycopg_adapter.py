from __future__ import annotations
from contextlib import asynccontextmanager, contextmanager
from typing import Optional

# psycopg 3.x (top-level imports)
try:
    from psycopg import Connection, AsyncConnection
except Exception as e:  # pragma: no cover
    raise RuntimeError("psycopg adapter requires psycopg>=3 installed") from e

# ---- attempt scopes (transaction/savepoint) ----


@contextmanager
def attempt_scope_sync(conn: Connection, *, read_only: bool):
    """
    Use a SAVEPOINT when already in a txn; otherwise start a txn.
    psycopg3 nested transaction blocks create savepoints automatically.
    """
    # Outer transaction (BEGIN) if needed
    with conn.transaction():
        # Nested -> savepoint, auto release/rollback
        with conn.transaction():
            if read_only:
                # Postgres: set read-only on this transaction block
                with conn.cursor() as cur:
                    cur.execute("SET TRANSACTION READ ONLY")
            yield


@asynccontextmanager
async def attempt_scope_async(conn: AsyncConnection, *, read_only: bool):
    async with conn.transaction():
        async with conn.transaction():
            if read_only:
                async with conn.cursor() as cur:
                    await cur.execute("SET TRANSACTION READ ONLY")
            yield


# ---- per-attempt timeouts (Postgres) ----


def apply_timeouts_sync(
    conn: Connection, *, lock_timeout_s: Optional[int], stmt_timeout_s: Optional[int]
) -> None:
    # Use SET LOCAL so it resets at block end
    with conn.cursor() as cur:
        if lock_timeout_s is not None:
            cur.execute(f"SET LOCAL lock_timeout = '{int(lock_timeout_s)}s'")
        if stmt_timeout_s is not None:
            cur.execute(f"SET LOCAL statement_timeout = '{int(stmt_timeout_s)}s'")


async def apply_timeouts_async(
    conn: AsyncConnection, *, lock_timeout_s: Optional[int], stmt_timeout_s: Optional[int]
) -> None:
    async with conn.cursor() as cur:
        if lock_timeout_s is not None:
            await cur.execute(f"SET LOCAL lock_timeout = '{int(lock_timeout_s)}s'")
        if stmt_timeout_s is not None:
            await cur.execute(f"SET LOCAL statement_timeout = '{int(stmt_timeout_s)}s'")
