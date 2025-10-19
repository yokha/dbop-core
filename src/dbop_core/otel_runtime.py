from __future__ import annotations

import os
import time
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple

from .core import execute, RetryPolicy


# --- Helpers for env flags ----------------------------------------------------


def _otel_enabled(explicit: Optional[bool]) -> bool:
    if explicit is not None:
        return explicit
    return os.getenv("DBOP_OTEL_ENABLED", "").lower() in {"1", "true", "yes", "on"}


def _metrics_enabled() -> bool:
    return os.getenv("DBOP_OTEL_METRICS_ENABLED", "").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


# --- Metrics plumbing (lazy / optional) --------------------------------------

try:
    from opentelemetry import metrics as _otel_metrics  # type: ignore[attr-defined]
except Exception:  # pragma: no cover - OTEL not installed
    _otel_metrics = None  # type: ignore[assignment]

_ops_counter = None
_attempts_counter = None
_duration_histogram = None
_metrics_instruments_ready = False


def _ensure_metrics() -> None:
    """
    Lazily create metric instruments if metrics are enabled and OTEL is available.
    Safe to call multiple times.
    """
    global _ops_counter, _attempts_counter, _duration_histogram, _metrics_instruments_ready

    if _metrics_instruments_ready:
        return

    if not _metrics_enabled():
        return

    if _otel_metrics is None:
        return

    meter = _otel_metrics.get_meter(__name__)

    _ops_counter = meter.create_counter(
        "dbop_operations_total",
        description="Total number of dbop-core operations.",
    )
    _attempts_counter = meter.create_counter(
        "dbop_attempts_total",
        description="Total number of dbop-core attempts (including retries).",
    )
    _duration_histogram = meter.create_histogram(
        "dbop_operation_duration_seconds",
        description="Latency of dbop-core operations.",
        unit="s",
    )

    _metrics_instruments_ready = True


# --- Traced execution ---------------------------------------------------------


async def execute_traced_optional(
    op: Callable[..., Any] | Callable[..., Awaitable[Any]],
    *,
    args: Tuple[Any, ...] = (),
    kwargs: Optional[Dict[str, Any]] = None,
    retry_on: Tuple[type[BaseException], ...] = (Exception,),
    classifier: Optional[Callable[[BaseException], bool]] = None,
    raises: bool = True,
    default: Any = None,
    policy: RetryPolicy = RetryPolicy(),
    attempt_scope: Optional[Callable[[bool], Any]] = None,  # sync CM factory
    attempt_scope_async: Optional[Callable[[bool], Awaitable[Any]]] = None,  # async CM factory
    pre_attempt: Optional[Callable[[], Awaitable[None]]] = None,
    read_only: bool = False,
    overall_timeout_s: Optional[float] = None,
    # tracing knobs (all optional)
    otel_enabled: Optional[bool] = None,  # None -> read env DBOP_OTEL_ENABLED
    span_name: str = "dbop.operation",
    base_attrs: Optional[Dict[str, Any]] = None,
    db_system: Optional[str] = None,
    db_user: Optional[str] = None,
    db_name: Optional[str] = None,
    db_statement: Optional[str] = None,  # redact upstream if needed
) -> Any:
    """
    Execute with tracing *if* OpenTelemetry is installed and enabled.
    Otherwise, falls back to plain `execute()` with zero overhead.

    When DBOP_OTEL_METRICS_ENABLED=1 (and OTEL metrics are available),
    this also emits:
      - dbop_operations_total
      - dbop_attempts_total
      - dbop_operation_duration_seconds
    """
    # Fast path: OTEL disabled entirely -> no tracing, no metrics
    if not _otel_enabled(otel_enabled):
        return await execute(
            op,
            args=args,
            kwargs=kwargs,
            retry_on=retry_on,
            classifier=classifier,
            raises=raises,
            default=default,
            policy=policy,
            attempt_scope=attempt_scope,
            attempt_scope_async=attempt_scope_async,
            pre_attempt=pre_attempt,
            read_only=read_only,
            overall_timeout_s=overall_timeout_s,
        )

    # Lazy import so this module stays importable without otel deps
    try:
        from opentelemetry import trace
        from opentelemetry.trace import SpanKind, Status, StatusCode
    except Exception:
        # Otel not installed -> silently fall back
        return await execute(
            op,
            args=args,
            kwargs=kwargs,
            retry_on=retry_on,
            classifier=classifier,
            raises=raises,
            default=default,
            policy=policy,
            attempt_scope=attempt_scope,
            attempt_scope_async=attempt_scope_async,
            pre_attempt=pre_attempt,
            read_only=read_only,
            overall_timeout_s=overall_timeout_s,
        )

    # Tracer + metrics instruments
    tracer = trace.get_tracer(__name__)

    _ensure_metrics()
    metrics_active = _metrics_instruments_ready and _metrics_enabled()

    attrs = {
        "db.system": db_system,
        "db.user": db_user,
        "db.name": db_name,
        "db.statement": db_statement if db_statement else None,
        "dbop.max_retries": policy.max_retries,
        "dbop.initial_delay": policy.initial_delay,
        "dbop.max_delay": policy.max_delay,
        "dbop.jitter": policy.jitter,
        "dbop.read_only": read_only,
        "dbop.overall_timeout_s": overall_timeout_s,
    }
    if base_attrs:
        attrs.update({k: v for k, v in base_attrs.items() if v is not None})

    metric_attrs_base = {
        "db.system": attrs["db.system"] or "unknown",
        "db.name": attrs["db.name"] or "unknown",
        "db.user": attrs["db.user"] or "unknown",
        "dbop.read_only": read_only,
    }

    # Build attempt-scoped wrappers lazily to avoid overhead when unused
    from contextlib import asynccontextmanager, contextmanager

    def set_attrs(span, d):
        for k, v in d.items():
            if v is not None:
                span.set_attribute(k, v)

    attempt_counter = {"n": 0}
    attempt_events = {"n": 0}

    def wrap_sync(factory):
        @contextmanager
        def cm(read_only: bool):
            attempt_counter["n"] += 1
            with tracer.start_as_current_span(f"{span_name}.attempt", kind=SpanKind.CLIENT) as s:
                set_attrs(
                    s,
                    {
                        **attrs,
                        "dbop.attempt.number": attempt_counter["n"],
                        "dbop.read_only": read_only,
                    },
                )
                try:
                    with factory(read_only):
                        yield
                    s.set_attribute("dbop.attempt.outcome", "success")
                except BaseException as exc:
                    s.record_exception(exc)
                    s.set_attribute("dbop.attempt.outcome", "error")
                    s.set_status(Status(StatusCode.ERROR))
                    raise

        return cm

    def wrap_async(factory):
        @asynccontextmanager
        async def cm(read_only: bool):
            attempt_counter["n"] += 1
            with tracer.start_as_current_span(f"{span_name}.attempt", kind=SpanKind.CLIENT) as s:
                set_attrs(
                    s,
                    {
                        **attrs,
                        "dbop.attempt.number": attempt_counter["n"],
                        "dbop.read_only": read_only,
                    },
                )
                try:
                    async with factory(read_only):
                        yield
                    s.set_attribute("dbop.attempt.outcome", "success")
                except BaseException as exc:
                    s.record_exception(exc)
                    s.set_attribute("dbop.attempt.outcome", "error")
                    s.set_status(Status(StatusCode.ERROR))
                    raise

        return cm

    traced_scope = wrap_sync(attempt_scope) if attempt_scope else None
    traced_scope_async = wrap_async(attempt_scope_async) if attempt_scope_async else None

    # Operation-level timing + outcome for metrics
    start = time.perf_counter()
    outcome = "success"  # optimistic; overwritten on error

    with tracer.start_as_current_span(span_name, kind=SpanKind.CLIENT) as root:
        set_attrs(root, attrs)
        # Optional: emit an event before each attempt via pre_attempt hook
        orig_pre = pre_attempt

        async def pre():
            # Count attempt events (works even when attempt_scope is not used)
            attempt_events["n"] += 1

            # metrics: per-attempt counter
            if metrics_active and _attempts_counter is not None:
                _attempts_counter.add(
                    1,
                    attributes=metric_attrs_base,
                )

            root.add_event(
                "dbop.pre_attempt",
                {"dbop.pre_attempt.count": attempt_events["n"]},
            )
            if orig_pre:
                await orig_pre()

        try:
            result = await execute(
                op,
                args=args,
                kwargs=kwargs,
                retry_on=retry_on,
                classifier=classifier,
                raises=raises,
                default=default,
                policy=policy,
                attempt_scope=traced_scope,
                attempt_scope_async=traced_scope_async,
                pre_attempt=pre,
                read_only=read_only,
                overall_timeout_s=overall_timeout_s,
            )
            root.set_attribute("dbop.outcome", "success")
            outcome = "success"
        except BaseException as exc:
            root.record_exception(exc)
            root.set_attribute("dbop.outcome", "error")
            root.set_status(Status(StatusCode.ERROR))
            outcome = "error"
            if raises:
                # record metrics before re-raising
                if metrics_active and _ops_counter is not None and _duration_histogram is not None:
                    duration = time.perf_counter() - start
                    metric_attrs = {
                        **metric_attrs_base,
                        "dbop.outcome": outcome,
                    }
                    _ops_counter.add(1, attributes=metric_attrs)
                    _duration_histogram.record(duration, attributes=metric_attrs)
                raise
            # raises == False -> fall back to default
            result = default
        else:
            # success path: record metrics
            if metrics_active and _ops_counter is not None and _duration_histogram is not None:
                duration = time.perf_counter() - start
                metric_attrs = {
                    **metric_attrs_base,
                    "dbop.outcome": outcome,
                }
                _ops_counter.add(1, attributes=metric_attrs)
                _duration_histogram.record(duration, attributes=metric_attrs)

        return result
