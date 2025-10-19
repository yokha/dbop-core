# -------- configurable vars --------
PYTHON    ?= python3
VENV      ?= .venv
PY        := $(VENV)/bin/python
PIP       := $(VENV)/bin/pip
TWINE     := $(VENV)/bin/twine
PYTEST    := $(VENV)/bin/pytest
RUFF      := $(VENV)/bin/ruff
BLACK     := $(VENV)/bin/black

PKG_IMPORT := dbop_core
PKG_DIST   := dbop-core

TEST_REPO_URL := https://test.pypi.org/legacy/
CUR_BRANCH    := $(shell git rev-parse --abbrev-ref HEAD)
PKG_FILE_PREFIX := $(PKG_IMPORT)

# Portable in-place sed (GNU vs BSD)
SED_INPLACE := $(shell sed --version >/dev/null 2>&1 && echo "-i" || echo "-i ''")

# -------- meta --------
.PHONY: help
help:
	@echo "Targets:"
	@echo "  venv                Create virtualenv"
	@echo "  install             Dev install (.[dev])"
	@echo "  install-fast        Same, uses 'uv pip' if available"
	@echo "  clean               Remove build/test artifacts"
	@echo "  clean-venv          Remove .venv"
	@echo "  fmt                 Format code with black"
	@echo "  lint                Lint with ruff"
	@echo "  fix                 Ruff --fix then format"
	@echo "  test                Run tests"
	@echo "  test-cov            Run tests with coverage (html/xml/term)"
	@echo "  dist                Build sdist+wheel"
	@echo "  check               Twine check dist/*"
	@echo "  smoke               Install wheel in fresh venv and import"
	@echo "  release-dry-run     dist -> check -> smoke"
	@echo "  publish-test        Upload to TestPyPI (uses $$TEST_PYPI_TOKEN)"
	@echo "  publish             Upload to PyPI (uses $$PYPI_TOKEN)"
	@echo "  bump VER=X.Y.Z      Bump version in pyproject (+ __init__ if present)"
	@echo "  tag VER=X.Y.Z       Create and push annotated tag vX.Y.Z"
	@echo "  tag-current         Tag current pyproject version"
	@echo "  untag VER=X.Y.Z     Delete remote+local tag vX.Y.Z"
	@echo "  check-version-sync  Ensure pyproject and __init__ versions match"
	@echo "  ensure-clean-tree   Fail if git has uncommitted changes"
	@echo "  test-examples       Run SQLite example smoke"
	@echo "  test-examples-pg    Run Postgres example smokes (Docker)"
	@echo "  test-examples-mysql Run MySQL example smoke (Docker)"
	@echo "  test-examples-all   Run all example smokes"
	@echo "  all                 Lint -> tests+coverage -> dist -> check -> smoke -> examples"
	@echo "  all-full            'all' + Postgres & MySQL example smokes (Docker)"

# -------- env --------
.PHONY: venv
venv:
	$(PYTHON) -m venv $(VENV)
	@echo "Activate with: source $(VENV)/bin/activate"

.PHONY: install
install: venv
	$(PIP) install -U pip
	$(PIP) install -e '.[dev]'

# try to use uv if present; falls back to pip
.PHONY: install-fast
install-fast: venv
	@if command -v uv >/dev/null 2>&1; then \
	  echo "Using uv"; uv pip install -e '.[dev]'; \
	else \
	  $(PIP) install -e '.[dev]'; \
	fi

# -------- hygiene --------
.PHONY: clean
clean:
	rm -rf .pytest_cache htmlcov .coverage coverage.xml dist build *.egg-info

.PHONY: clean-venv
clean-venv:
	rm -rf $(VENV)

# -------- quality --------
.PHONY: fmt
fmt:
	$(BLACK) src tests

.PHONY: lint
lint:
	$(RUFF) check src tests

.PHONY: fix
fix:
	$(RUFF) check --fix src tests
	$(BLACK) src tests

# -------- tests & coverage --------
# Exclude integration by default; set INTEGRATION=1 to include them
ifeq ($(INTEGRATION),1)
  PYTEST_MARK :=
else
  PYTEST_MARK := -m "not integration"
endif

.PHONY: test
test:
	$(PYTEST) -q $(PYTEST_MARK)

test-cov:
	rm -rf .coverage htmlcov coverage.xml
	@$(PIP) install -q "pytest-cov>=4.1" "coverage>=7.4"
	$(PYTEST) -m "not integration" \
	  --cov=src/$(PKG_IMPORT) --cov-report=term-missing --cov-report=xml --cov-report=html

.PHONY: cov-open
cov-open:
	@xdg-open htmlcov/index.html >/dev/null 2>&1 || true

# -------- build & publish --------
.PHONY: dist
dist: venv clean check-version-sync
	$(PIP) install -U build
	$(PY) -m build
	@ls -lh dist/

.PHONY: check
check: venv
	$(PIP) install -U twine
	$(TWINE) check dist/*

# quick smoke test: install wheel into temp venv & import
.PHONY: smoke
smoke:
	@rm -rf .venv-smoke
	$(PYTHON) -m venv .venv-smoke
	@set -e; \
	echo "dist/ contains:"; ls -l dist || true; \
	ART=""; \
	if ls dist/$(PKG_FILE_PREFIX)-*.whl >/dev/null 2>&1; then \
	  ART=$$(ls -1 dist/$(PKG_FILE_PREFIX)-*.whl | head -n1); \
	elif ls dist/$(PKG_FILE_PREFIX)-*.tar.gz >/dev/null 2>&1; then \
	  ART=$$(ls -1 dist/$(PKG_FILE_PREFIX)-*.tar.gz | head -n1); \
	else \
	  echo "No built artifacts matching dist/$(PKG_FILE_PREFIX)-*.{whl,tar.gz} found."; \
	  exit 2; \
	fi; \
	. .venv-smoke/bin/activate && python -m pip install --no-input --no-cache-dir "$$ART"; \
	. .venv-smoke/bin/activate && python -c "import importlib; m=importlib.import_module('$(PKG_IMPORT)'); print('Imported:', m.__name__, 'version:', getattr(m,'__version__','n/a'))"
	@rm -rf .venv-smoke

.PHONY: release-dry-run
release-dry-run: dist check smoke

publish-test: ensure-clean-tree
	@test -n "$$TEST_PYPI_TOKEN" || (echo "TEST_PYPI_TOKEN not set" && exit 2)
	$(TWINE) upload --verbose --skip-existing --repository-url $(TEST_REPO_URL) dist/* \
	  -u __token__ -p $$TEST_PYPI_TOKEN

publish: ensure-clean-tree dist
	@test -n "$$PYPI_TOKEN" || (echo "PYPI_TOKEN not set" && exit 2)
	$(TWINE) upload --non-interactive --verbose --skip-existing dist/* \
	  -u __token__ -p $$PYPI_TOKEN

.PHONY: release-testpypi
release-testpypi: release-dry-run publish-test

.PHONY: release-pypi
release-pypi: release-dry-run publish

# -------- tagging / versioning --------
# Extract current version from pyproject
CUR_VER := $(shell grep -Po '(?<=^version = ")[^"]+' pyproject.toml)

.PHONY: bump
bump: ensure-clean-tree
	@[ -n "$(VER)" ] || (echo "Usage: make bump VER=X.Y.Z" && exit 2)
	@sed $(SED_INPLACE) 's/^version = ".*"/version = "$(VER)"/' pyproject.toml
	@if grep -q "__version__" src/$(PKG_IMPORT)/__init__.py 2>/dev/null; then \
	  sed $(SED_INPLACE) 's/^__version__ = ".*"/__version__ = "$(VER)"/' src/$(PKG_IMPORT)/__init__.py; \
	fi
	git add pyproject.toml src/$(PKG_IMPORT)/__init__.py 2>/dev/null || true
	git commit -m "chore(version): bump to v$(VER)"

.PHONY: tag
tag: ensure-clean-tree check-version-sync
	@[ -n "$(VER)" ] || (echo "Usage: make tag VER=X.Y.Z" && exit 2)
	git tag -a v$(VER) -m "v$(VER)"
	git push origin $(CUR_BRANCH) --tags

# Convenience: tag current pyproject version without specifying VER
.PHONY: tag-current
tag-current: ensure-clean-tree check-version-sync
	@git tag -a v$(CUR_VER) -m "v$(CUR_VER)"
	@git push origin $(CUR_BRANCH) --tags

# Optional GH release (needs `gh auth login` done once)
.PHONY: gh-release
gh-release:
	@[ -n "$(VER)" ] || (echo "Usage: make gh-release VER=X.Y.Z" && exit 2)
	@command -v gh >/dev/null || (echo "Install GitHub CLI: https://cli.github.com"; exit 2)
	gh release create v$(VER) dist/* --title "v$(VER)" --notes "See CHANGELOG.md"

# -------- safety checks --------
.PHONY: check-version-sync
check-version-sync:
	$(PY) scripts/check_version_sync.py $(PKG_IMPORT)

.PHONY: ensure-clean-tree
ensure-clean-tree:
	@git update-index -q --refresh
	@if ! git diff-index --quiet HEAD --; then \
	  echo "Working tree not clean. Commit or stash changes first."; \
	  exit 2; \
	fi

# -------- examples smoke tests --------
EXAMPLES_DIR := examples

.PHONY: examples-init-env
examples-init-env:
	@# Ensure examples/.env exists (for Docker-backed samples)
	@[ -f $(EXAMPLES_DIR)/.env ] || cp -n $(EXAMPLES_DIR)/env.example $(EXAMPLES_DIR)/.env || true

# Run a couple of quick examples by default (SQLite variants)
.PHONY: test-examples
test-examples: test-examples-sqlite test-examples-aiosqlite

# --- SQLite (SQLAlchemy sync) ---
.PHONY: test-examples-sqlite
test-examples-sqlite:
	$(MAKE) -C $(EXAMPLES_DIR) clean-venv
	$(MAKE) -C $(EXAMPLES_DIR) venv
	$(MAKE) -C $(EXAMPLES_DIR) install-sqlite-local DBOP_CORE_PATH='..'
	$(MAKE) -C $(EXAMPLES_DIR) run-sqlite

# --- SQLite (aiosqlite async) ---
.PHONY: test-examples-aiosqlite
test-examples-aiosqlite:
	$(MAKE) -C $(EXAMPLES_DIR) venv
	$(MAKE) -C $(EXAMPLES_DIR) install-aiosqlite-local DBOP_CORE_PATH='..'
	$(MAKE) -C $(EXAMPLES_DIR) run-aiosqlite

# --- Postgres (psycopg & asyncpg) ---
.PHONY: test-examples-pg
test-examples-pg: examples-init-env
	@command -v docker >/dev/null 2>&1 || { echo "Docker not found; skipping Postgres examples"; exit 0; }
	$(MAKE) -C $(EXAMPLES_DIR) pg-up
	$(MAKE) -C $(EXAMPLES_DIR) install-psycopg-local DBOP_CORE_PATH='..'
	$(MAKE) -C $(EXAMPLES_DIR) run-psycopg
	$(MAKE) -C $(EXAMPLES_DIR) install-asyncpg-local DBOP_CORE_PATH='..'
	$(MAKE) -C $(EXAMPLES_DIR) run-asyncpg
	$(MAKE) -C $(EXAMPLES_DIR) pg-down

# --- MySQL (PyMySQL sync + aiomysql async) ---
.PHONY: test-examples-mysql
test-examples-mysql: examples-init-env
	@command -v docker >/dev/null 2>&1 || { echo "Docker not found; skipping MySQL examples"; exit 0; }
	$(MAKE) -C $(EXAMPLES_DIR) mysql-up
	$(MAKE) -C $(EXAMPLES_DIR) install-mysql-local DBOP_CORE_PATH='..'
	$(MAKE) -C $(EXAMPLES_DIR) run-mysql
	$(MAKE) -C $(EXAMPLES_DIR) install-aiomysql-local DBOP_CORE_PATH='..'
	$(MAKE) -C $(EXAMPLES_DIR) run-aiomysql
	$(MAKE) -C $(EXAMPLES_DIR) mysql-down

# --- Everything ---
.PHONY: test-examples-all
test-examples-all: test-examples-sqlite test-examples-aiosqlite test-examples-pg test-examples-mysql

# --- integration tests -------------------------------------------------------
.PHONY: ensure-psycopg ensure-asyncpg ensure-mysql-drivers
ensure-psycopg:
	@$(PIP) -q install 'psycopg[binary]>=3.1.8'

ensure-asyncpg:
	@$(PIP) -q install 'asyncpg>=0.29'

ensure-mysql-drivers:
	@$(PIP) -q install 'pymysql' 'aiomysql' 'cryptography>=42'

# Postgres (Docker) helpers
.PHONY: _pg-up _pg-down _pg-wait
_pg-up:
	@[ -f examples/.env ] || cp -n examples/env.example examples/.env || true
	docker compose -f examples/_compose/postgres.yml --env-file examples/.env up -d

_pg-down:
	docker compose -f examples/_compose/postgres.yml --env-file examples/.env down -v

_pg-wait:
	@set -e; \
	CID=$$(docker compose -f examples/_compose/postgres.yml --env-file examples/.env ps -q pg); \
	echo "Waiting for Postgres (container $$CID)…"; \
	i=0; \
	while ! docker exec $$CID pg_isready -U "$$POSTGRES_USER" -d "$$POSTGRES_DB" >/dev/null 2>&1; do \
	  i=$$((i+1)); \
	  if [ $$i -gt 60 ]; then \
	    echo "Postgres did not become ready in time"; \
	    docker logs $$CID || true; \
	    exit 2; \
	  fi; \
	  sleep 1; \
	done; \
	echo "Postgres is ready."

# MySQL (Docker) helpers
.PHONY: _mysql-up _mysql-down _mysql-wait
_mysql-up:
	@[ -f examples/.env ] || cp -n examples/env.example examples/.env || true
	docker compose -f examples/_compose/mysql.yml --env-file examples/.env up -d

_mysql-down:
	docker compose -f examples/_compose/mysql.yml --env-file examples/.env down -v

_mysql-wait:
	@set -e; \
	CID=$$(docker compose -f examples/_compose/mysql.yml --env-file examples/.env ps -q mysql); \
	echo "Waiting for MySQL (container $$CID)…"; \
	i=0; \
	while ! docker exec $$CID sh -lc 'mysqladmin ping -h 127.0.0.1 -u$$MYSQL_USER -p$$MYSQL_PASSWORD --silent' >/dev/null 2>&1; do \
	  i=$$((i+1)); \
	  if [ $$i -gt 90 ]; then \
	    echo "MySQL did not become ready in time"; \
	    docker logs $$CID || true; \
	    exit 2; \
	  fi; \
	  sleep 1; \
	done; \
	echo "MySQL is ready."

# --- PG (psycopg) integration test ------------------------------------------
.PHONY: test-int-deadlocks-pg
test-int-deadlocks-pg:
	@set -e; \
	$(MAKE) _pg-up; \
	$(MAKE) _pg-wait; \
	$(MAKE) ensure-psycopg; \
	POSTGRES_DSN=$$(awk -F= '/^POSTGRES_DSN=/{print $$2}' examples/.env); \
	echo "Using TEST_PG_DSN=$$POSTGRES_DSN"; \
	rc=0; \
	TEST_PG_DSN="$$POSTGRES_DSN" $(PYTEST) -q -v -m integration tests/integration/test_deadlocks_postgres.py || rc=$$?; \
	# Treat 'no tests collected' as success (module-level skip)
	if [ $$rc -eq 5 ]; then echo "(psycopg tests skipped — OK)"; rc=0; fi; \
	$(MAKE) _pg-down; \
	exit $$rc

# --- PG (asyncpg) integration test ------------------------------------------
.PHONY: test-int-deadlocks-asyncpg
test-int-deadlocks-asyncpg:
	@set -e; \
	$(MAKE) _pg-up; \
	$(MAKE) _pg-wait; \
	$(MAKE) ensure-asyncpg; \
	POSTGRES_DSN=$$(awk -F= '/^POSTGRES_DSN=/{print $$2}' examples/.env); \
	echo "Using TEST_PG_DSN=$$POSTGRES_DSN"; \
	rc=0; \
	TEST_PG_DSN="$$POSTGRES_DSN" $(PYTEST) -q -v -m integration tests/integration/test_deadlocks_asyncpg.py || rc=$$?; \
	if [ $$rc -eq 5 ]; then echo "(asyncpg tests skipped — OK)"; rc=0; fi; \
	$(MAKE) _pg-down; \
	exit $$rc

# --- MySQL (pymysql) integration test ---------------------------------------
.PHONY: test-int-deadlocks-mysql
test-int-deadlocks-mysql:
	@set -e; \
	docker compose -f examples/_compose/mysql.yml --env-file examples/.env up -d; \
	$(MAKE) ensure-mysql-drivers; \
	$(MAKE) _mysql-wait; \
	# Resolve mapped port robustly
	CID=$$(docker compose -f examples/_compose/mysql.yml --env-file examples/.env ps -q mysql); \
	HP=$$(docker compose -f examples/_compose/mysql.yml --env-file examples/.env port mysql 3306 2>/dev/null | awk 'NF{print; exit}'); \
	PORT=$${HP##*:}; \
	[ -n "$$PORT" ] || PORT=$$(docker inspect -f '{{ (index (index .NetworkSettings.Ports "3306/tcp") 0).HostPort }}' $$CID 2>/dev/null || echo 53306); \
	HOST=127.0.0.1; USER=$${MYSQL_USER:-dbop}; PASS=$${MYSQL_PASSWORD:-dbop}; DB=$${MYSQL_DB:-dbop}; \
	echo "Using MySQL on $$HOST:$$PORT (db=$$DB user=$$USER)"; \
	rc=0; \
	TEST_MYSQL_HOST=$$HOST TEST_MYSQL_PORT=$$PORT TEST_MYSQL_USER=$$USER TEST_MYSQL_PASSWORD=$$PASS TEST_MYSQL_DB=$$DB \
	$(PYTEST) -q -v -m integration tests/integration/test_deadlocks_mysql.py || rc=$$?; \
	if [ $$rc -eq 5 ]; then echo "(pymysql tests skipped — OK)"; rc=0; fi; \
	docker compose -f examples/_compose/mysql.yml --env-file examples/.env down -v; \
	exit $$rc

# --- MySQL (aiomysql) integration test --------------------------------------
.PHONY: test-int-deadlocks-aiomysql
test-int-deadlocks-aiomysql:
	@set -e; \
	docker compose -f examples/_compose/mysql.yml --env-file examples/.env up -d; \
	$(MAKE) ensure-mysql-drivers; \
	$(MAKE) _mysql-wait; \
	CID=$$(docker compose -f examples/_compose/mysql.yml --env-file examples/.env ps -q mysql); \
	HP=$$(docker compose -f examples/_compose/mysql.yml --env-file examples/.env port mysql 3306 2>/dev/null | awk 'NF{print; exit}'); \
	PORT=$${HP##*:}; \
	[ -n "$$PORT" ] || PORT=$$(docker inspect -f '{{ (index (index .NetworkSettings.Ports "3306/tcp") 0).HostPort }}' $$CID 2>/dev/null || echo 53306); \
	HOST=127.0.0.1; USER=$${MYSQL_USER:-dbop}; PASS=$${MYSQL_PASSWORD:-dbop}; DB=$${MYSQL_DB:-dbop}; \
	echo "Using MySQL on $$HOST:$$PORT (db=$$DB user=$$USER)"; \
	rc=0; \
	TEST_MYSQL_HOST=$$HOST TEST_MYSQL_PORT=$$PORT TEST_MYSQL_USER=$$USER TEST_MYSQL_PASSWORD=$$PASS TEST_MYSQL_DB=$$DB \
	$(PYTEST) -q -v -m integration tests/integration/test_deadlocks_aiomysql.py || rc=$$?; \
	if [ $$rc -eq 5 ]; then echo "(aiomysql tests skipped — OK)"; rc=0; fi; \
	docker compose -f examples/_compose/mysql.yml --env-file examples/.env down -v; \
	exit $$rc

# --- All integrations --------------------------------------------------------
.PHONY: test-int-deadlocks-all
test-int-deadlocks-all: test-int-deadlocks-pg test-int-deadlocks-asyncpg test-int-deadlocks-mysql test-int-deadlocks-aiomysql
	@echo "All integration deadlock tests completed."

# -------- one-button flows --------
.PHONY: all
all:
	$(MAKE) lint
	$(MAKE) test-cov
	$(MAKE) dist
	$(MAKE) check
	$(MAKE) smoke
	$(MAKE) test-examples-all

.PHONY: all-full
all-full:
	$(MAKE) test-examples-pg
	$(MAKE) test-examples-mysql
