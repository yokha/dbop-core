import asyncio
import os
import random

from dbop_core.core import RetryPolicy
from dbop_core.otel_setup import init_tracer, init_metrics
from dbop_core.otel_runtime import execute_traced_optional

# Enable tracing / metrics via env (can still be disabled by user)
os.environ.setdefault("DBOP_OTEL_ENABLED", "1")

# Defaults for local collector
os.environ.setdefault("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4317")


async def flaky_op(ctx: dict) -> str:
    """
    Simple demo op:
    - fails randomly with RuntimeError (to trigger retries)
    - sleeps a bit to generate non-zero latency
    """
    if random.random() < ctx["fail_prob"]:
        raise RuntimeError("transient boom in dbop-core smoke demo")

    # Simulate some work
    await asyncio.sleep(random.uniform(0.02, 0.15))
    return "ok"


async def main() -> None:
    # Configure exporter from env:
    #   DBOP_OTEL_EXPORTER=http  (default)
    #   DBOP_OTEL_EXPORTER=grpc
    exporter = os.getenv("DBOP_OTEL_EXPORTER", "http").lower()
    if exporter not in ("http", "grpc"):
        print(f"[dbop-core] Unknown DBOP_OTEL_EXPORTER={exporter!r}, falling back to 'http'")
        exporter = "http"

    service_name = "dbop-core-otel-smoke"

    # Init tracing + metrics
    init_tracer(service_name=service_name, exporter=exporter)
    init_metrics(service_name=service_name, exporter=exporter)

    # How many operations / how flaky?
    n_ops = int(os.getenv("DBOP_SMOKE_OPS", "50"))
    fail_prob = float(os.getenv("DBOP_SMOKE_FAIL_PROB", "0.5"))

    print(f"[dbop-core] running smoke: n_ops={n_ops}, fail_prob={fail_prob}, exporter={exporter}")

    policy = RetryPolicy(
        max_retries=2,
        initial_delay=0.05,
        max_delay=0.1,
        jitter=0.0,
    )

    # Run operations sequentially (good enough for demo)
    for i in range(n_ops):
        ctx = {"fail_prob": fail_prob}

        try:
            result = await execute_traced_optional(
                op=lambda: flaky_op(ctx),
                policy=policy,
                retry_on=(RuntimeError,),
                read_only=False,
                otel_enabled=True,          # explicit opt-in
                span_name="dbop.smoke",
                db_system="test",
                db_name="example",
                db_user="example",
                db_statement="flaky_op()",  # no real SQL, just a label
                base_attrs={
                    "dbop.demo_op_index": i,
                },
            )
            print(f"[dbop-core] op #{i} -> {result}")
        except Exception as exc:
            # If all retries fail, we still record spans + metrics
            print(f"[dbop-core] op #{i} failed after retries: {exc!r}")

    print("[dbop-core] smoke run complete")


if __name__ == "__main__":
    asyncio.run(main())
