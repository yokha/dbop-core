from __future__ import annotations
import itertools
import pytest
from dbop_core.core import execute, RetryPolicy


class Boom(RuntimeError):
    pass


@pytest.mark.asyncio
async def test_retries_then_succeeds():
    calls = itertools.count()

    async def sometimes(x):
        i = next(calls)
        if i < 2:
            raise Boom("boom")
        return x * 2

    policy = RetryPolicy(max_retries=3, initial_delay=0.01, max_delay=0.02, jitter=0.0)
    out = await execute(
        sometimes,
        args=(21,),
        retry_on=(Boom,),
        classifier=lambda e: True,
        policy=policy,
    )
    assert out == 42
