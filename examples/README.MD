# dbop-core — Examples

Practical examples demonstrating how to use **`dbop-core`** with different Python database drivers and ORMs.

Includes both **sync** and **async** backends:

* **SQLAlchemy + SQLite** (sync)
* **aiosqlite + SQLite** (async)
* **psycopg 3 + Postgres** (async)
* **asyncpg + Postgres** (async)
* **PyMySQL + MySQL/MariaDB** (sync)
* **aiomysql + MySQL/MariaDB** (async)

---

## Overview

Each subfolder is a self-contained runnable example with its own `main.py` and `requirements.txt`.
All examples share a single `Makefile` for convenience.

```text
examples/
├── Makefile
├── env.example             # rename to .env for docker-based examples
├── example.db              # local SQLite DB (used by SQLite examples)
├── _compose/               # lightweight Docker Compose files
│   ├── postgres.yml
│   └── mysql.yml
│
├── sqlalchemy-sqlite/
│   ├── main.py
│   └── requirements.txt
│
├── aiosqlite-sqlite/
│   ├── main.py
│   └── requirements.txt
│
├── psycopg-postgres/
│   ├── main.py
│   └── requirements.txt
│
├── asyncpg-postgres/
│   ├── main.py
│   └── requirements.txt
│
├── mysql-pymysql/
│   ├── main.py
│   └── requirements.txt
│
└── aiomysql-mysql/
    ├── main.py
    └── requirements.txt
```

---

## Conceptual Layout

```text
 ┌────────────────────────────┐
 │         dbop-core          │  ← your local or installed package
 └────────────┬───────────────┘
              │
              ▼
       examples/Makefile
       ├─────────────────────────────┐
       │                             │
   SQLite (local)                Docker Compose services
   ├─ sqlalchemy-sqlite          ├─ _compose/postgres.yml
   └─ aiosqlite-sqlite           └─ _compose/mysql.yml
       │                             │
       ▼                             ▼
  Runs main.py                 Launches Postgres/MySQL containers
  directly on host             for async/sync examples
```

---

## Prerequisites

* **Python 3.9+**
* **Docker** (for Postgres/MySQL examples)
* `make` (optional but recommended)

---

## Getting Started

```bash
cd examples
cp env.example .env    # configure ports/credentials if needed
```

### A) SQLite (no Docker required)

**SQLAlchemy (sync)**

```bash
make install-sqlite
make run-sqlite
```

**aiosqlite (async)**

```bash
make install-aiosqlite
make run-aiosqlite
```

---

### B) Postgres (Docker)

Start the container:

```bash
make pg-up
```

Run async examples:

```bash
make install-psycopg && make run-psycopg
make install-asyncpg && make run-asyncpg
```

Tear down:

```bash
make pg-down
```

---

### C) MySQL / MariaDB (Docker)

Start the container:

```bash
make mysql-up
```

Run examples:

```bash
make install-mysql && make run-mysql
make install-aiomysql && make run-aiomysql
```

Tear down:

```bash
make mysql-down
```

---

## Environment Variables

All database settings are loaded from `.env`. Defaults from `env.example`:

```env
# Postgres
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=dbop
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
POSTGRES_DSN=postgresql://postgres:postgres@127.0.0.1:5432/dbop

# MySQL
MYSQL_ROOT_PASSWORD=root
MYSQL_DB=dbop
MYSQL_USER=dbop
MYSQL_PASSWORD=dbop
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
```

> ⚙️ Adjust ports if they’re in use.
> The `pg-up` and `mysql-up` targets automatically read these values.

---

## What Each Example Demonstrates

* **Retries & exponential backoff** via `RetryPolicy`
* **Attempt scopes** for transactions or SAVEPOINT retries
* **Per-attempt timeouts**:

  * PostgreSQL -> `lock_timeout`, `statement_timeout`
  * MySQL/MariaDB -> `innodb_lock_wait_timeout`, `MAX_EXECUTION_TIME`
  * SQLite -> `PRAGMA busy_timeout`
* **Classifier logic** using `dbapi_classifier` to detect transient errors

> `dbop_core.execute()` is always async; sync examples wrap it in `asyncio.run()`.

---

## Run Examples Against Local Source

If developing locally, install `dbop-core` in editable mode:

```bash
# from examples/
python -m venv .venv
source .venv/bin/activate
pip install -e ..[sqlalchemy]
```

Or use:

```bash
DBOP_CORE_PATH='..' make install-psycopg-local
```

---

## Troubleshooting

**Authentication error (MySQL 8+)**

> Default plugin is `caching_sha2_password`; `PyMySQL`/`aiomysql` may need `cryptography`.

Fix:

```bash
pip install cryptography
```

Or run MySQL with:

```
--default-authentication-plugin=mysql_native_password
```

**Port already in use**

```bash
make pg-down && make pg-up
# or
make mysql-down && make mysql-up
```

**Import errors**
Run the matching `install-*` target before execution.

**Slow startup / hanging**
Containers may still be initializing. Retry after a few seconds.

---

## Cleanup

```bash
make pg-down
make mysql-down
make clean-venv
```

---

## Explore Further

* Try inducing deadlocks or long locks to see **retries and backoff** in action.
* Customize `classifier(exc)` to fine-tune what counts as transient.
* Extend examples with **custom RetryPolicy** or **OTLP tracing** once integrated.

---
