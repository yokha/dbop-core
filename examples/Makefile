# One venv for all examples
PYTHON   ?= python3
VENV     ?= .venv
PY       := $(VENV)/bin/python
PIP      := $(VENV)/bin/pip

EX_DIR   := $(CURDIR)

.PHONY: help
help:
	@echo "Examples:"
	@echo "  venv                   Create virtualenv for examples"
	@echo "  install-sqlite         Install deps for SQLAlchemy+SQLite example"
	@echo "  run-sqlite             Run SQLAlchemy+SQLite example"
	@echo "  pg-up                  Start local Postgres (docker-compose)"
	@echo "  pg-down                Stop Postgres"
	@echo "  install-psycopg        Install deps for psycopg example"
	@echo "  run-psycopg            Run psycopg example (needs Postgres up + .env)"
	@echo "  install-asyncpg        Install deps for asyncpg example"
	@echo "  run-asyncpg            Run asyncpg example (needs Postgres up + .env)"
	@echo "  clean-venv             Remove examples venv"

.PHONY: venv
venv:
	$(PYTHON) -m venv $(VENV)
	@echo "Activate with: source $(VENV)/bin/activate"

# ---- SQLite (SQLAlchemy) ----
.PHONY: install-sqlite
install-sqlite: venv
	$(PIP) install -U pip
	# install from PyPI:
	$(PIP) install -r sqlalchemy-sqlite/requirements.txt
	# or, if developing locally against the parent repo, uncomment next line:
	# $(PIP) install -e ..[sqlalchemy]

.PHONY: run-sqlite
run-sqlite:
	$(PY) sqlalchemy-sqlite/main.py

# ---- Postgres infra ----
.PHONY: pg-up
pg-up:
	docker compose -f _compose/postgres.yml --env-file .env up -d

.PHONY: pg-down
pg-down:
	docker compose -f _compose/postgres.yml --env-file .env down -v

# ---- MySQL/MariaDB infra ----
.PHONY: mysql-up
mysql-up:
	docker compose -f _compose/mysql.yml --env-file .env up -d

.PHONY: mysql-down
mysql-down:
	docker compose -f _compose/mysql.yml --env-file .env down -v

# ---- pymysql example ----
.PHONY: install-mysql
install-mysql: venv
	$(PIP) install -U pip
	$(PIP) install -r mysql-pymysql/requirements.txt
	# or local dev:
	# $(PIP) install -e ..

.PHONY: run-mysql
run-mysql:
	$(PY) mysql-pymysql/main.py

# ---- psycopg ----
.PHONY: install-psycopg
install-psycopg: venv
	$(PIP) install -U pip
	$(PIP) install -r psycopg-postgres/requirements.txt
	# or local dev:
	# $(PIP) install -e ..[psycopg]

.PHONY: run-psycopg
run-psycopg:
	$(PY) psycopg-postgres/main.py

# ---- asyncpg ----
.PHONY: install-asyncpg
install-asyncpg: venv
	$(PIP) install -U pip
	$(PIP) install -r asyncpg-postgres/requirements.txt
	# or local dev:
	# $(PIP) install -e ..[asyncpg]

.PHONY: run-asyncpg
run-asyncpg:
	$(PY) asyncpg-postgres/main.py

# ---------- aiosqlite ----------
.PHONY: install-aiosqlite
install-aiosqlite: venv
	$(PIP) install -U pip
	$(PIP) install -r aiosqlite-sqlite/requirements.txt

.PHONY: install-aiosqlite-local
install-aiosqlite-local: venv
	$(PIP) install -U pip
	$(PIP) install -e '$(DBOP_CORE_PATH)[aiosqlite]'

.PHONY: run-aiosqlite
run-aiosqlite:
	$(PY) aiosqlite-sqlite/main.py

# ---------- aiomysql ----------
.PHONY: install-aiomysql
install-aiomysql: venv
	$(PIP) install -U pip
	$(PIP) install -r aiomysql-mysql/requirements.txt

.PHONY: install-aiomysql-local
install-aiomysql-local: venv
	$(PIP) install -U pip
	$(PIP) install -e '$(DBOP_CORE_PATH)[aiomysql]'
	$(PIP) install python-dotenv cryptography

.PHONY: run-aiomysql
run-aiomysql:
	$(PY) aiomysql-mysql/main.py

.PHONY: quick-sqlite
quick-sqlite: install-aiosqlite-local run-aiosqlite

.PHONY: quick-mysql
quick-mysql: mysql-up install-aiomysql-local run-aiomysql mysql-down

.PHONY: clean-venv
clean-venv:
	rm -rf $(VENV)


# Path to your local dbop-core repo
DBOP_CORE_PATH ?= ..

.PHONY: install-sqlite-local
install-sqlite-local: venv
	$(PIP) install -U pip
	$(PIP) install -e '$(DBOP_CORE_PATH)[sqlalchemy]'

.PHONY: install-psycopg-local
install-psycopg-local: venv
	$(PIP) install -U pip
	$(PIP) install -e '$(DBOP_CORE_PATH)[psycopg]'
	$(PIP) install python-dotenv

.PHONY: install-asyncpg-local
install-asyncpg-local: venv
	$(PIP) install -U pip
	$(PIP) install -e '$(DBOP_CORE_PATH)[asyncpg]'
	$(PIP) install python-dotenv

.PHONY: install-mysql-local
install-mysql-local: venv
	$(PIP) install -U pip
	$(PIP) install -e '$(DBOP_CORE_PATH)'
	$(PIP) install pymysql python-dotenv cryptography
