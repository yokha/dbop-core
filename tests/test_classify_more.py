import pytest
import types
from dbop_core.classify import dbapi_classifier
from dbop_core.core import execute

class Transient(RuntimeError): pass
class Fatal(RuntimeError): pass

@pytest.mark.asyncio
async def test_classifier_false_prevents_retry():
    async def op(): raise Transient("X")
    with pytest.raises(Transient):
        await execute(op, retry_on=(Transient,), classifier=lambda e: False)

@pytest.mark.asyncio
async def test_retry_on_excludes_exception():
    async def op(): raise Fatal("no retry")
    with pytest.raises(Fatal):
        await execute(op, retry_on=(Transient,))


# --- Helpers --------------------------------------------------------------

class OpErr(Exception):
    """Mimic DB-API OperationalError by name for the generic branch."""
    pass

def exc_with_orig_errno(errno: int, msg="boom"):
    e = Exception("wrapper")
    orig = types.SimpleNamespace(args=(errno, msg))
    e.orig = orig
    return e

# --- PostgreSQL message branches (lines ~17,19) ---------------------------

def test_pg_message_statement_timeout():
    e = Exception("canceling statement due to statement timeout")
    assert dbapi_classifier(e) is True

def test_pg_message_lock_timeout_or_deadlock():
    e1 = Exception("deadlock detected")
    e2 = Exception("canceling statement due to lock timeout")
    assert dbapi_classifier(e1) is True
    assert dbapi_classifier(e2) is True

# --- MySQL errno branches (lines ~27–28) ----------------------------------

def test_mysql_errno_via_orig_args():
    # 2006/2013 are connection hiccups → True
    e = exc_with_orig_errno(2006, "server has gone away")
    assert dbapi_classifier(e) is True

def test_mysql_errno_via_self_args():
    # If no .orig, classifier reads exc.args[0]
    e = OpErr(2013, "lost connection during query")
    assert dbapi_classifier(e) is True

def test_mysql_nowait_and_lockwait_messages():
    assert dbapi_classifier(Exception("NOWAIT is set")) is True
    assert dbapi_classifier(Exception("Lock wait timeout exceeded")) is True

# --- Generic op/timeout-ish (lines ~49–60) --------------------------------

class OperationalError(Exception):
    """Name matters for the generic branch."""

def test_generic_operational_timeout_by_type_and_msg():
    # type name matches AND message contains a trigger token
    e = OperationalError("connection reset by peer")
    assert dbapi_classifier(e) is True

def test_generic_operational_timeout_via_orig_type():
    # exc type doesn't match, but .orig type name does
    e = Exception("timeout while waiting")
    e.orig = OperationalError("inner")
    assert dbapi_classifier(e) is True

def test_non_transient_falls_through():
    assert dbapi_classifier(Exception("syntax error at or near SELECT")) is False
