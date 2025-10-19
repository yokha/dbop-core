#!/usr/bin/env python3
"""
Verify that project version in pyproject.toml matches package __version__.
Usage: python scripts/check_version_sync.py [pkg_import]
Default pkg_import = "dbop_core"
"""
from __future__ import annotations
import sys
import pathlib
import importlib

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # Python 3.9–3.10
    import tomli as tomllib  # type: ignore[no-redef]

pkg_import = sys.argv[1] if len(sys.argv) > 1 else "dbop_core"

root = pathlib.Path(".").resolve()
with open(root / "pyproject.toml", "rb") as f:
    pyproj = tomllib.load(f)

ver_toml = pyproj["project"]["version"]

# import package from src/
sys.path.insert(0, str(root / "src"))
pkg = importlib.import_module(pkg_import)
ver_pkg = getattr(pkg, "__version__", None)

if ver_toml != ver_pkg:
    raise SystemExit(f"Version mismatch: pyproject={ver_toml} != package={ver_pkg}")

print(f"Version OK: {ver_toml}")
