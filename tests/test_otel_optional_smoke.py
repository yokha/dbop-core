import pytest
from dbop_core.otel_runtime import execute_traced_optional
from dbop_core.core import RetryPolicy


@pytest.mark.asyncio
async def test_tracing_disabled_fast_path():
    async def op():
        return 7

    out = await execute_traced_optional(op, otel_enabled=False, policy=RetryPolicy(max_retries=0))
    assert out == 7
