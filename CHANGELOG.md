# Changelog

All notable changes to this project will be documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)
and adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2025-11-17

### Added

* **Optional OpenTelemetry (OTLP) observability**
  * New `execute_traced_optional()` helper exposed from the package.
  * `dbop_core.otel_setup` – helpers to initialize OTEL tracer + metrics exporters
    (HTTP or gRPC) based on `DBOP_OTEL_EXPORTER` and standard `OTEL_EXPORTER_OTLP_*`
    env vars.
  * `dbop_core.otel_runtime` – traced wrapper around `execute()` that emits:
    * a parent span per logical DB operation,
    * per-attempt spans with outcome and attributes,
    * attributes such as `dbop.max_retries`, `dbop.initial_delay`,
      `dbop.outcome`, `db.system`, `db.name`, …
  * Optional Prometheus-style OTLP metrics:
    * `dbop_attempts_total` – total attempts (including retries),
    * `dbop_operations_total` – total logical operations,
    * `dbop_operation_duration_seconds` – histogram of operation latency.

* **Examples + Docker demo**
  * `examples/otel-smoke/` – smoke test that drives retries and emits spans/metrics.
  * `_compose/otel.yml` – local OTEL stack (collector + Jaeger + Prometheus + Grafana).
  * `examples/OTEL-dashboard.json` – sample Grafana dashboard for dbop metrics.

### Notes

* OTEL integration is **disabled by default**.
* Enabling requires the `otel` extra and `DBOP_OTEL_ENABLED=1`.
* If `opentelemetry-sdk` is not installed, imports safely degrade to no-op.


## [1.0.0] - 2025-10-19

### Added

* **Core execution engine**

  * Async + sync **attempt scopes** with retries, exponential backoff (with jitter), and per-attempt timeout support.
  * Pluggable **transient error classifier** (`dbapi_classifier` by default).
  * **Pre-attempt hooks** for query-level timeout injection or instrumentation.
* **Contrib adapters** *(fully implemented)*:

  * `psycopg_adapter` – sync/async attempt scopes with Postgres timeout handling.
  * `asyncpg_adapter` – async attempt scopes and Postgres `lock_timeout` integration.
  * `dbapi_adapter` – generic DB-API 2.0 adapter supporting Postgres/MySQL/SQLite timeouts.
  * `aiomysql_adapter` – async MySQL adapter with scoped retries and per-query timeout support.
  * `aiosqlite_adapter` – lightweight async adapter for SQLite.
  * `sqlalchemy_adapter` – thin convenience wrapper for SQLAlchemy (sync).
  * `sqlalchemy_adapter_async` – async variant for SQLAlchemy 2.x async engines/sessions.
* **Retry policy framework**

  * Configurable max retries, exponential backoff, and jitter.
  * Pluggable `RetryPolicy` to extend custom retry strategies.
* **Extensive test suite**

  * Async + sync coverage for all contrib adapters.
  * Example coverage for SQLite, Postgres (`psycopg` / `asyncpg`), and MySQL (`aiomysql` / `PyMySQL`).
  * > 90 % combined coverage (measured with `pytest-cov`).
* **Developer tooling**

  * Added `Makefile` with `init`, `lint`, `format`, `test`, `cov`, `clean`.
  * Added `pyproject.toml` with **Ruff** configuration for linting/formatting.
  * Added **uv** support for fast venv setup and ephemeral tool execution.
  * Integrated `pytest-xdist` for parallel test execution.
* **Documentation & examples**

  * Basic usage examples for each adapter.
  * PoC notes for Raspberry Pi / Docker SDK + NFS development environment.

### Notes

* Python 3.9 – 3.12 supported.
* ORM-agnostic: any connection or session layer can integrate via adapters.
