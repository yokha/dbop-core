from __future__ import annotations

from contextlib import asynccontextmanager, suppress
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@asynccontextmanager
async def attempt_scope_async(sess: AsyncSession, read_only: bool = False):
    """
    SQLAlchemy AsyncSession attempt scope:
      - Prefer begin_nested() (SAVEPOINT) when possible
      - Fallback to outer begin() if needed
      - Best-effort READ ONLY transaction attribute
    """
    tx = None
    # Try nested first
    try:
        tx = await sess.begin_nested()
    except Exception:
        tx = await sess.begin()

    try:
        if read_only:
            with suppress(Exception):
                await sess.execute(text("SET TRANSACTION READ ONLY"))
        yield
        await tx.commit()
    except Exception:
        with suppress(Exception):
            await tx.rollback()
        raise
