# dbop-core

**DB-agnostic retry runner** for Python database operations.
You bring the driver or ORM — `dbop-core` gives you:

* **Retries with backoff and jitter**
* **Attempt scopes** (transaction / SAVEPOINT wrappers)
* **Per-attempt hooks** (e.g. set timeouts, apply metadata)
* **Transient error classification**

Lightweight and composable — the core doesn’t know your driver.
Adapters live under `contrib/` (SQLAlchemy, psycopg, asyncpg, aiomysql, aiosqlite, and generic DB-API).

---

## When to Use

Use `dbop-core` when you need **resilience for a single logical DB step**:

* Occasional **deadlocks** or **lock wait timeouts**
* **Slow statements** that risk blocking your pool
* **SAVEPOINT-style retries** inside an outer transaction
* **Per-attempt timeouts** without rewriting your app logic

It’s not a migration tool or pooler — just a precise **execution runner** for safe retries.

---

## Features

* ✅ **Async-first core API**, works with sync *and* async drivers
* 🔁 **Retry policy**: max retries, exponential backoff, jitter, caps
* 🧩 **Attempt scopes**: pluggable context managers (transaction/savepoint)
* ⚙️ **Per-attempt hooks**: run custom setup (timeouts, instrumentation)
* 🧠 **Transient classifier**: decide whether an exception should retry

---

## Installation

```bash
pip install dbop-core

# optional extras for contrib adapters
pip install "dbop-core[sqlalchemy]"
pip install "dbop-core[psycopg]"
pip install "dbop-core[asyncpg]"
pip install "dbop-core[aiomysql]"
pip install "dbop-core[aiosqlite]"
```

**Compatibility:** Python 3.9 – 3.13

---

## Quickstart

```python
from dbop_core.core import execute, RetryPolicy

async def op(x):
    return x * 2

result = await execute(op, args=(21,), policy=RetryPolicy())
assert result == 42
```

---

## Core API (Essentials)

```python
await execute(
    op,                        # callable: sync or async
    args=(), kwargs=None,
    retry_on=(Exception,),     # types to retry
    classifier=None,           # fn(exc) -> bool; True = retry
    raises=True,               # if False, return default on final failure
    default=None,
    policy=RetryPolicy(),      # backoff/jitter settings
    attempt_scope=None,        # sync AttemptScope
    attempt_scope_async=None,  # async AttemptScope
    pre_attempt=None,          # async setup hook
    read_only=False,           # passed to scopes
    overall_timeout_s=None,    # per-attempt timeout
)
```

**Semantics**

* Only exceptions in `retry_on` are candidates for retry.
* If `classifier` is provided, it takes precedence per exception (`True` → retry, `False` → stop).
* `overall_timeout_s` cancels the attempt; if `raises=False`, you get `default`.
* `pre_attempt` is always async — even for sync drivers (wrap your sync setup with `async def pre(): ...`).
---
### Execution Flow (Conceptual Diagram)

Below is a simplified view of what happens inside `execute()` during retries.

```text
 ┌──────────────────────────────────────────────────────────────┐
 │                     execute() lifecycle                      │
 └──────────────────────────────────────────────────────────────┘
            │
            ▼
    [1] start execute()
            │
            │
            ▼
    [2] initialize RetryPolicy
        - max_retries, delay, jitter, etc.
        - retry_on exception types
            │
            ▼
    [3] for each attempt (1..N):
            │
            ├─► [3.1] pre_attempt()
            │        (async setup hook)
            │        e.g., apply_timeouts, reset state
            │
            ├─► [3.2] attempt_scope / attempt_scope_async
            │        (transaction or SAVEPOINT wrapper)
            │
            ├─► [3.3] call op(*args, **kwargs)
            │        (sync or async function)
            │
            ├─► [3.4] if success → return result
            │
            ├─► [3.5] if exception:
            │       ├─ check type in retry_on
            │       ├─ run classifier(exc)
            │       ├─ if transient → sleep(backoff) → retry
            │       └─ else → re-raise (or return default)
            │
            ▼
    [4] if all retries failed:
        - return default (if raises=False)
        - or raise last exception
```

**Key concepts:**

* `attempt_scope` isolates one DB operation (transaction or savepoint).
  If the attempt fails, the scope rolls back and prepares for retry.
* `pre_attempt` runs before each try — perfect for **timeouts**, **instrumentation**, or **context tagging**.
* `RetryPolicy` determines how long to wait and how many times to retry.

---

### Design Philosophy

Database operations often need **fine-grained resilience** — but frameworks usually give you an all-or-nothing approach:

* Retry at the HTTP or ORM layer (too coarse).
* Manual retry loops around transactions (too error-prone).
* Connection poolers that retry implicitly (too opaque).

`dbop-core` exists to make retries **explicit, minimal, and driver-agnostic**.
It focuses on **one unit of work** — one statement, one transaction, one savepoint — and lets *you* decide:

* ✅ *When to retry* (`classifier`, `retry_on`)
* ✅ *How to retry* (`RetryPolicy`, exponential backoff + jitter)
* ✅ *Where to isolate* (`attempt_scope` / `attempt_scope_async`)
* ✅ *What to prepare* before each try (`pre_attempt` hook)

Everything else — connection pooling, ORM sessions, schema migration — stays out of scope.
This separation keeps `dbop-core` **composable**, **transparent**, and **safe** to embed anywhere in your stack — from raw DB-API connections to async SQLAlchemy sessions or FastAPI background tasks.

> In short: **`dbop-core` doesn’t manage your database. It helps you survive it.**

---

**Execution modes:**

| Driver Type | Scope used            | Hook type                | Example Adapter                       |
| ----------- | --------------------- | ------------------------ | ------------------------------------- |
| Sync        | `attempt_scope`       | `apply_timeouts_sync()`  | DB-API, SQLAlchemy                    |
| Async       | `attempt_scope_async` | `apply_timeouts_async()` | asyncpg, psycopg, aiomysql, aiosqlite |

---

## Contrib Adapters

| Adapter                   | Sync/Async | Backend               | File                                  |
| ------------------------- | ---------- | --------------------- | ------------------------------------- |
| DB-API (generic)          | Sync       | Postgres/MySQL/SQLite | `contrib/dbapi_adapter.py`            |
| SQLAlchemy (Session)      | Sync       | Any                   | `contrib/sqlalchemy_adapter.py`       |
| SQLAlchemy (AsyncSession) | Async      | Any                   | `contrib/sqlalchemy_adapter_async.py` |
| psycopg 3                 | Async      | Postgres              | `contrib/psycopg_adapter.py`          |
| asyncpg                   | Async      | Postgres              | `contrib/asyncpg_adapter.py`          |
| aiomysql                  | Async      | MySQL/MariaDB         | `contrib/aiomysql_adapter.py`         |
| aiosqlite                 | Async      | SQLite                | `contrib/aiosqlite_adapter.py`        |

---

### SQLAlchemy (Sync Example)

```python
import asyncio
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dbop_core.core import execute, RetryPolicy
from dbop_core.contrib.sqlalchemy_adapter import attempt_scope_sync

engine = create_engine("sqlite+pysqlite:///:memory:")
Session = sessionmaker(bind=engine)

def setup(sess):
    sess.execute(text("CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT)"))
def put(sess, k, v):
    sess.execute(text("INSERT OR REPLACE INTO kv VALUES (:k,:v)"), {"k": k, "v": v})
def get(sess, k):
    return sess.execute(text("SELECT v FROM kv WHERE k=:k"), {"k": k}).scalar()

async def main():
    pol = RetryPolicy(max_retries=3, initial_delay=0.05, max_delay=0.2)
    with Session() as sess:
        with sess.begin(): setup(sess)

        with sess.begin():
            await execute(lambda: put(sess, "hello", "world"),
                attempt_scope=lambda r=False: attempt_scope_sync(sess, read_only=r),
                policy=pol)

        with sess.begin():
            val = await execute(lambda: get(sess, "hello"),
                attempt_scope=lambda r=False: attempt_scope_sync(sess, read_only=r),
                policy=pol, read_only=True)
            print(val)

asyncio.run(main())
```

---

### psycopg (Postgres, Async)

```python
from functools import partial
from psycopg import AsyncConnection
from dbop_core.core import execute, RetryPolicy
from dbop_core.classify import dbapi_classifier
from dbop_core.contrib.psycopg_adapter import attempt_scope_async, apply_timeouts_async

DSN = "postgresql://postgres:postgres@localhost:5432/dbop"

async def pre(conn):  # per-attempt setup
    await apply_timeouts_async(conn, lock_timeout_s=3, stmt_timeout_s=10)

async def run():
    async with AsyncConnection.connect(DSN) as conn:
        pol = RetryPolicy(max_retries=5, initial_delay=0.05, max_delay=0.5)

        await execute(
            lambda: conn.execute("INSERT INTO items(name) VALUES ('gamma') ON CONFLICT DO NOTHING"),
            classifier=dbapi_classifier,
            attempt_scope_async=lambda r=False: attempt_scope_async(conn, read_only=r),
            pre_attempt=partial(pre, conn),
            policy=pol,
        )

        count = await execute(
            lambda: conn.execute("SELECT COUNT(*) FROM items"),
            classifier=dbapi_classifier,
            attempt_scope_async=lambda r=False: attempt_scope_async(conn, read_only=r),
            pre_attempt=partial(pre, conn),
            policy=pol, read_only=True,
        )
        print("count:", count)
```

---

### Generic DB-API (Sync, e.g. SQLite)

```python
import asyncio, sqlite3
from dbop_core.core import execute, RetryPolicy
from dbop_core.contrib.dbapi_adapter import attempt_scope_sync, apply_timeouts_sync

conn = sqlite3.connect(":memory:")

def create(): conn.execute("CREATE TABLE IF NOT EXISTS t(x INT)")
def insert(): conn.execute("INSERT INTO t(x) VALUES (1)")
def count(): return conn.execute("SELECT COUNT(*) FROM t").fetchone()[0]

async def pre():
    apply_timeouts_sync(conn, backend="sqlite", lock_timeout_s=3)

async def main():
    create()
    pol = RetryPolicy(max_retries=2, initial_delay=0.05, max_delay=0.2)

    await execute(lambda: insert(),
        attempt_scope=lambda r=False: attempt_scope_sync(conn, read_only=r, backend="sqlite"),
        pre_attempt=pre, policy=pol)

    n = await execute(lambda: count(),
        attempt_scope=lambda r=False: attempt_scope_sync(conn, read_only=True, backend="sqlite"),
        pre_attempt=pre, policy=pol, read_only=True)
    print("rows:", n)

asyncio.run(main())
```

---

## Timeout Mapping (per attempt)

| Backend           | Mechanism                                                      |
| ----------------- | -------------------------------------------------------------- |
| **PostgreSQL**    | `SET LOCAL lock_timeout`, `SET LOCAL statement_timeout`        |
| **MySQL/MariaDB** | `innodb_lock_wait_timeout`, `MAX_EXECUTION_TIME` (best-effort) |
| **SQLite**        | `PRAGMA busy_timeout` (connection-level)                       |

Use your adapter’s `apply_timeouts_*` in `pre_attempt()`.

---

## Transient Classification

`dbapi_classifier` detects common transient patterns:

| Backend       | Typical Transient Codes / Messages               |
| ------------- | ------------------------------------------------ |
| Postgres      | `40P01` (deadlock), `55P03` (lock not available) |
| MySQL/MariaDB | `1213`, `1205`, connection lost                  |
| SQLite        | `database is locked`                             |
| Generic       | Operational/timeouts from DB-API                 |

You can always plug in your own classifier:
`classifier(exc) -> bool`.

---

## Examples

```bash
cd examples
cp .env.sample .env  # configure DSNs

# SQLite (local)
make install-sqlite-local && make run-sqlite

# Postgres (Docker)
make pg-up && make install-psycopg-local && make run-psycopg
make install-asyncpg-local && make run-asyncpg
make pg-down

# MySQL (Docker)
make mysql-up && make install-mysql-local && make run-mysql
make mysql-down
```

---

## Roadmap

* OTLP tracing (spans around retries)
* Instrumentation hooks (OpenTelemetry / Prometheus)
* More contrib adapters (`databases`, `gino`, etc.)
* Extended cookbook examples

---

## Changelog

See [CHANGELOG.md](CHANGELOG.md)

---

## License

MIT

---

## Author

**Youssef Khaya**
[LinkedIn](https://www.linkedin.com/in/youssef-khaya-88a1a128)
[GitHub](https://github.com/yokha/dbop-core)

---

### Optional badges for later

Once you publish to PyPI and GitHub Actions:

```markdown
[![PyPI version](https://img.shields.io/pypi/v/dbop-core.svg)](https://pypi.org/project/dbop-core/)
[![Build Status](https://github.com/yokha/dbop-core/actions/workflows/test.yml/badge.svg)](https://github.com/yokha/dbop-core/actions)
[![Coverage Status](https://img.shields.io/codecov/c/github/yokha/dbop-core.svg)](https://codecov.io/gh/yokha/dbop-core)
```

---
