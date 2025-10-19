# **dbop-core — Examples**

Practical, runnable examples demonstrating how to use **`dbop-core`** with multiple databases:

* SQLite (sync + async)
* PostgreSQL (asyncpg, psycopg)
* MySQL / MariaDB (PyMySQL + aiomysql)
* Full **OTLP Observability stack** (Collector + Jaeger + Prometheus + Grafana)

Each example shows:

* Retries with exponential backoff
* Attempt-scoped retries (transaction/savepoint)
* Per-attempt timeouts
* Transient classification
* Optional OpenTelemetry instrumentation

---

# **Directory Layout**

```text
examples/
├── Makefile
├── env.example                  # rename to .env for DB examples
├── example.db                   # used by SQLite examples
├── _compose/
│   ├── postgres.yml             # Postgres via Docker
│   ├── mysql.yml                # MySQL/MariaDB via Docker
│   └── otel.yml                 # OTEL Collector + Jaeger + Prometheus + Grafana
│
├── sqlalchemy-sqlite/           # Sync SQLite example (ORM)
│   ├── main.py
│   └── requirements.txt
│
├── aiosqlite-sqlite/            # Async SQLite example
│   ├── main.py
│   └── requirements.txt
│
├── psycopg-postgres/
│   ├── main.py                  # Async psycopg example
│   └── requirements.txt
│
├── asyncpg-postgres/
│   ├── main.py                  # Async asyncpg example
│   └── requirements.txt
│
├── mysql-pymysql/
│   ├── main.py                  # Sync MySQL
│   └── requirements.txt
│
├── aiomysql-mysql/
│   ├── main.py                  # Async MySQL
│   └── requirements.txt
│
└── otel-smoke/
    ├── main.py                  # OTEL tracing + metrics smoke demo
    ├── grafana/                 # Sample dashboard
    │   └── dashboard-dbop.json
    └── requirements.txt
```

---

# **1. SQLite Examples (No Docker Required)**

## Sync SQLAlchemy

```bash
make install-sqlite
make run-sqlite
```

## Async aiosqlite

```bash
make install-aiosqlite
make run-aiosqlite
```

---

# **2. PostgreSQL Examples (Docker)**

Start Postgres:

```bash
make pg-up
```

Run psycopg (async):

```bash
make install-psycopg
make run-psycopg
```

Run asyncpg:

```bash
make install-asyncpg
make run-asyncpg
```

Shutdown:

```bash
make pg-down
```

---

# **3. MySQL / MariaDB Examples (Docker)**

Start MySQL:

```bash
make mysql-up
```

Run sync example:

```bash
make install-mysql
make run-mysql
```

Run async example:

```bash
make install-aiomysql
make run-aiomysql
```

Shutdown:

```bash
make mysql-down
```

---

# **4. OpenTelemetry Smoke Demo (Traces + Metrics)**

The OTEL smoke demo shows:

* Operation spans
* Attempt spans
* Retry events
* Prometheus metrics
* Grafana dashboard

## Start the full OTEL stack:

```bash
make otel-up
```

This launches:

| Component      | Address                                          |
| -------------- | ------------------------------------------------ |
| OTEL Collector | 4317 gRPC, 4318 HTTP, 9464 Prom metrics          |
| Jaeger UI      | [http://localhost:16686](http://localhost:16686) |
| Prometheus     | [http://localhost:9090](http://localhost:9090)   |
| Grafana        | [http://localhost:3000](http://localhost:3000)   |

Login to Grafana:

```
user: admin
pass: admin
```

Then import:

```
otel-smoke/grafana/dashboard-dbop.json
```

---

## Run the smoke script (HTTP exporter)

```bash
make otel-smoke-local-http
```

## Or gRPC exporter:

```bash
make otel-smoke-local-grpc
```

You should see:

* Traces in Jaeger → service `dbop-core-otel-smoke`
* DB operation counters in Prometheus
* Latency histogram + counters in Grafana

---

# **5. Env Variables**

Copy:

```bash
cp env.example .env
```

Key values:

```
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
POSTGRES_DB=dbop

MYSQL_USER=dbop
MYSQL_PASSWORD=dbop
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_DB=dbop
```

For OTEL:

```
DBOP_OTEL_ENABLED=1
DBOP_OTEL_EXPORTER=http    # or grpc
OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4317
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:4318/v1/traces
OTEL_EXPORTER_OTLP_METRICS_ENDPOINT=http://127.0.0.1:4318/v1/metrics
```

---

# **6. What Each Example Demonstrates**

| Example          | Shows                                           |
| ---------------- | ----------------------------------------------- |
| SQLite           | Basic retry logic, busy_timeout                 |
| SQLAlchemy       | Nested attempt scopes via ORM transactions      |
| psycopg          | `SET LOCAL lock_timeout`, async retries         |
| asyncpg          | Savepoint retry strategy                        |
| MySQL / aiomysql | `innodb_lock_wait_timeout` + MAX_EXECUTION_TIME |
| otel-smoke       | Traces + metrics + Grafana dashboard            |

---

# **7. Developing Locally**

Install local source:

```bash
cd examples
python -m venv .venv
source .venv/bin/activate
pip install -e ..
```

Or with extras:

```bash
pip install -e ..[otel]
pip install -e ..[psycopg]
```

---

# **8. Cleanup**

```bash
make pg-down
make mysql-down
make otel-down
make clean-venv
```

---

# **9. Troubleshooting**

**MySQL auth error**

```
pip install cryptography
```

**Prometheus shows data but Grafana doesn’t**

* Ensure Prometheus datasource is added in Grafana
* Import the dashboard
* Wait 5–10s (scrape interval)

**Jaeger shows no traces**

* Check `DBOP_OTEL_ENABLED=1`
* Check exporter: `DBOP_OTEL_EXPORTER=http|grpc`
