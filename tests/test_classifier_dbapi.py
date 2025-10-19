from __future__ import annotations
from types import SimpleNamespace
from dbop_core.classify import dbapi_classifier


def test_pg_deadlock_by_code():
    exc = SimpleNamespace(pgcode="40P01", orig=None)
    assert dbapi_classifier(exc) is True


def test_mysql_errno_deadlock():
    orig = SimpleNamespace(args=(1213, "Deadlock found"))
    exc = SimpleNamespace(orig=orig)
    assert dbapi_classifier(exc) is True


def test_sqlite_locked_message():
    class E(Exception):
        pass

    exc = E("database is locked")
    assert dbapi_classifier(exc) is True


def test_non_transient_generic():
    class E(Exception):
        pass

    exc = E("syntax error at or near SELECT")  # not a transient hint
    assert dbapi_classifier(exc) is False
