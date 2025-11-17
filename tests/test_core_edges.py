import asyncio
import pytest
from dbop_core.core import execute, RetryPolicy


class Transient(RuntimeError):
    pass


class Fatal(RuntimeError):
    pass


@pytest.mark.asyncio
async def test_classifier_false_stops_immediately(monkeypatch):
    calls = {"n": 0}

    async def op():
        calls["n"] += 1
        raise Transient("should not retry if classifier returns False")

    # classifier says "do not retry"
    with pytest.raises(Transient):
        await execute(op, retry_on=(Transient,), classifier=lambda e: False)
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_raises_false_returns_default(monkeypatch):
    async def op():
        raise Transient()

    res = await execute(op, retry_on=(Transient,), raises=False, default="fallback")
    assert res == "fallback"


@pytest.mark.asyncio
async def test_overall_timeout_hits_default(monkeypatch):
    async def op():
        await asyncio.sleep(0.2)

    res = await execute(op, overall_timeout_s=0.05, raises=False, default="timeout")
    assert res == "timeout"
