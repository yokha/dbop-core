import asyncio
import importlib
import os

import pytest

from dbop_core import RetryPolicy, execute_traced_optional
import dbop_core.otel_setup as otel_setup

async def _dummy_op(value: int = 1) -> int:
    return value


@pytest.mark.asyncio
async def test_execute_traced_optional_explicitly_disabled():
    """
    If otel_enabled=False, execute_traced_optional should:
    - NOT try to import opentelemetry
    - Just delegate to core.execute()
    This path must work even if opentelemetry-sdk is not installed.
    """
    # Ensure the env var does not accidentally override
    os.environ.pop("DBOP_OTEL_ENABLED", None)

    policy = RetryPolicy(max_retries=2)

    result = await execute_traced_optional(
        op=_dummy_op,
        args=(42,),
        policy=policy,
        otel_enabled=False,  # <- force OTEL off
    )

    assert result == 42


@pytest.mark.asyncio
async def test_execute_traced_optional_env_disabled_by_default():
    """
    When otel_enabled=None and DBOP_OTEL_ENABLED is unset/false-y,
    the helper should behave like plain execute() as well.
    """
    os.environ.pop("DBOP_OTEL_ENABLED", None)

    policy = RetryPolicy(max_retries=1)

    result = await execute_traced_optional(
        op=_dummy_op,
        args=(7,),
        policy=policy,
        otel_enabled=None,  # use env check path
    )

    assert result == 7


def test_otel_setup_does_not_crash_without_sdk(monkeypatch):
    """
    init_tracer / init_metrics must be safe even if opentelemetry-sdk
    is not installed. We only assert that they don't raise.
    """

    # If you want to be extra-paranoid, you can force a reload to
    # ensure we see the current code:
    importlib.reload(otel_setup)

    # These should simply no-op (or log) when OTEL deps are missing.
    otel_setup.init_tracer(service_name="test-svc", exporter="http")
    otel_setup.init_metrics(service_name="test-svc", exporter="http")
