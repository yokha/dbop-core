from __future__ import annotations
import pytest
from contextlib import AbstractContextManager, AbstractAsyncContextManager
from dbop_core.core import execute, RetryPolicy


class ScopeSync(AbstractContextManager):
    def __init__(self, log):
        self.log = log

    def __enter__(self):
        self.log.append("enter-sync")

    def __exit__(self, exc_type, exc, tb):
        self.log.append("exit-sync")


class ScopeAsync(AbstractAsyncContextManager):
    def __init__(self, log):
        self.log = log

    async def __aenter__(self):
        self.log.append("enter-async")

    async def __aexit__(self, exc_type, exc, tb):
        self.log.append("exit-async")


@pytest.mark.asyncio
async def test_sync_op_uses_sync_scope():
    log = []

    def op_sync():
        return "ok"

    out = await execute(
        op_sync,
        attempt_scope=lambda read_only=False: ScopeSync(log),
        policy=RetryPolicy(max_retries=0),
    )
    assert out == "ok"
    assert log == ["enter-sync", "exit-sync"]


@pytest.mark.asyncio
async def test_async_op_uses_async_scope():
    log = []

    async def op_async():
        return "ok"

    out = await execute(
        op_async,
        attempt_scope_async=lambda read_only=False: ScopeAsync(log),
        policy=RetryPolicy(max_retries=0),
    )
    assert out == "ok"
    assert log == ["enter-async", "exit-async"]
