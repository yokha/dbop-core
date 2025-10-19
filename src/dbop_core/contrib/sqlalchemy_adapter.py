from __future__ import annotations
from contextlib import asynccontextmanager, contextmanager, suppress
from sqlalchemy import text
from sqlalchemy.exc import InvalidRequestError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session


@contextmanager
def attempt_scope_sync(sess: Session, *, read_only: bool):
    try:
        tx = sess.begin_nested()
        try:
            if read_only:
                with suppress(Exception):
                    sess.execute(text("SET TRANSACTION READ ONLY"))
            yield
            tx.commit()
            return
        except InvalidRequestError:
            with suppress(Exception):
                tx.rollback()
        except Exception:
            try:
                tx.rollback()
            except Exception as rb_exc:
                if "does not exist" not in str(rb_exc).lower():
                    raise
            raise
    except InvalidRequestError:
        pass
    tx = sess.begin()
    try:
        if read_only:
            with suppress(Exception):
                sess.execute(text("SET TRANSACTION READ ONLY"))
        yield
        tx.commit()
    except Exception:
        with suppress(Exception):
            tx.rollback()
        raise


@asynccontextmanager
async def attempt_scope_async(sess: AsyncSession, *, read_only: bool):
    try:
        tx = await sess.begin_nested()
        try:
            if read_only:
                with suppress(Exception):
                    await sess.execute(text("SET TRANSACTION READ ONLY"))
            yield
            await tx.commit()
            return
        except InvalidRequestError:
            with suppress(Exception):
                await tx.rollback()
        except Exception:
            try:
                await tx.rollback()
            except Exception as rb_exc:
                if "does not exist" not in str(rb_exc).lower():
                    raise
            raise
    except InvalidRequestError:
        pass
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
