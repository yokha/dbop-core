from __future__ import annotations
import itertools
import pytest
from dbop_core.core import execute, RetryPolicy


class Boom(RuntimeError):
    pass


@pytest.mark.asyncio
async def test_pre_attempt_invoked_per_attempt():
    calls = itertools.count()
    pre_calls = []

    async def op():
        i = next(calls)
        if i < 2:
            raise Boom("boom")
        return "ok"

    async def pre_attempt():
        pre_calls.append("pre")

    out = await execute(
        op,
        retry_on=(Boom,),
        classifier=lambda e: True,  # treat Boom as transient
        policy=RetryPolicy(max_retries=3, initial_delay=0.001, max_delay=0.001, jitter=0.0),
        pre_attempt=pre_attempt,
    )
    assert out == "ok"
    # 3 attempts total -> pre_attempt called 3 times
    assert len(pre_calls) == 3
