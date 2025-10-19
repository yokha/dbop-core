from __future__ import annotations
import asyncio
import pytest
from dbop_core.core import execute, RetryPolicy


@pytest.mark.asyncio
async def test_overall_timeout_raises_when_not_retried():
    async def slow():
        await asyncio.sleep(0.2)
        return 1

    with pytest.raises(asyncio.TimeoutError):
        await execute(
            slow,
            retry_on=(),  # do NOT catch; let TimeoutError bubble
            overall_timeout_s=0.05,
            policy=RetryPolicy(max_retries=2, initial_delay=0.01, max_delay=0.02, jitter=0.0),
        )


@pytest.mark.asyncio
async def test_overall_timeout_with_default_when_not_raises():
    async def slow():
        await asyncio.sleep(0.2)
        return 1

    out = await execute(
        slow,
        retry_on=(),  # don't catch timeout
        overall_timeout_s=0.01,
        raises=False,
        default={"timed_out": True},
        policy=RetryPolicy(max_retries=1, initial_delay=0.001, max_delay=0.001, jitter=0.0),
    )
    assert out == {"timed_out": True}
