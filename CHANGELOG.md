# Changelog

All notable changes to this project will be documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)
and adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
