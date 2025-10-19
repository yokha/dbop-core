from __future__ import annotations
import pytest
from dbop_core.core import execute, RetryPolicy


class Always(RuntimeError):
    pass


@pytest.mark.asyncio
async def test_returns_default_on_exhaustion_when_raises_false():
    async def fail():
        raise Always("nope")

    policy = RetryPolicy(max_retries=2, initial_delay=0.01, max_delay=0.02, jitter=0.0)
    out = await execute(
        fail,
        retry_on=(Always,),
        raises=False,
        default={"ok": False},
        policy=policy,
        classifier=lambda e: True,
    )
    assert out == {"ok": False}
