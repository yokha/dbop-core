from __future__ import annotations
import pytest
from dbop_core.core import execute, RetryPolicy


class Boom(RuntimeError):
    pass


@pytest.mark.asyncio
async def test_non_transient_no_retry():
    attempts = []

    async def op():
        attempts.append(1)
        raise Boom("not transient")

    # classifier says: never retry
    out = None
    out = await execute(
        op,
        retry_on=(Boom,),
        classifier=lambda e: False,  # non-transient
        raises=False,
        default="fallback",
        policy=RetryPolicy(max_retries=5, initial_delay=0.01, max_delay=0.02, jitter=0.0),
    )
    assert out == "fallback"
    assert len(attempts) == 1  # no retries
