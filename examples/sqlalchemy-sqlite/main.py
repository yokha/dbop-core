from __future__ import annotations
import asyncio
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dbop_core.core import execute, RetryPolicy
from dbop_core.contrib.sqlalchemy_adapter import attempt_scope_sync

# SQLite in-memory engine
engine = create_engine("sqlite+pysqlite:///:memory:", echo=False, connect_args={"timeout": 1})
Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

def setup(sess):
    sess.execute(text("CREATE TABLE IF NOT EXISTS items(id INTEGER PRIMARY KEY, name TEXT)"))
    sess.execute(text("DELETE FROM items"))
    sess.execute(text("INSERT INTO items(name) VALUES ('alpha'), ('beta')"))

def insert_one(sess, name: str):
    sess.execute(text("INSERT INTO items(name) VALUES (:n)"), {"n": name})

def select_all(sess):
    return [tuple(r) for r in sess.execute(text("SELECT id, name FROM items ORDER BY id")).all()]

async def main():
    policy = RetryPolicy(max_retries=2, initial_delay=0.01, max_delay=0.05, jitter=0.0)

    with Session() as sess:
        # 1) Prepare base data (no retries needed)
        with sess.begin():
            setup(sess)

        # 2) Write step (await execute!)
        with sess.begin():
            await execute(
                lambda: insert_one(sess, "gamma"),
                attempt_scope=lambda read_only=False: attempt_scope_sync(sess, read_only=read_only),
                policy=policy,
            )

        # 3) Read step (read_only scope + await execute)
        with sess.begin():
            rows = await execute(
                lambda: select_all(sess),
                attempt_scope=lambda read_only=False: attempt_scope_sync(sess, read_only=True),
                policy=policy,
                read_only=True,
            )
            print("Rows:", rows)

if __name__ == "__main__":
    asyncio.run(main())
