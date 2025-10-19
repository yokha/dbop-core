from __future__ import annotations

import os
from typing import Optional

# We keep imports in a try/except so that dbop-core still works even if
# opentelemetry is not installed (OTEL layer becomes a no-op).
try:
    from opentelemetry import trace, metrics
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    # Traces: HTTP vs gRPC exporters
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
        OTLPSpanExporter as OTLPHttpSpanExporter,
    )
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
        OTLPSpanExporter as OTLPGrpcSpanExporter,
    )

    # Metrics: HTTP vs gRPC exporters
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
        OTLPMetricExporter as OTLPHttpMetricExporter,
    )
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
        OTLPMetricExporter as OTLPGrpcMetricExporter,
    )

    _OTEL_AVAILABLE = True
except Exception:  # pragma: no cover - graceful fallback when OTEL is missing
    _OTEL_AVAILABLE = False

    # Dummy placeholders so type checkers don’t complain
    TracerProvider = object  # type: ignore[assignment]
    MeterProvider = object  # type: ignore[assignment]


_tracer_provider: Optional[TracerProvider] = None
_meter_provider: Optional[MeterProvider] = None


def _build_resource(service_name: str) -> "Resource":
    """
    Common Resource for both traces and metrics.

    You can override the version from the environment if you want to align it
    with your package version or your app version.
    """
    service_version = os.getenv("DBOP_SERVICE_VERSION", "dev")
    return Resource.create(
        {
            "service.name": service_name,
            "service.version": service_version,
        }
    )


# ---------------------------------------------------------------------------
# Traces
# ---------------------------------------------------------------------------


def init_tracer(service_name: str = "dbop-core-demo", exporter: str = "http") -> None:
    """
    Initialize a TracerProvider + OTLP exporter.

    :param service_name: logical service name (appears in Jaeger, Tempo, etc.)
    :param exporter: "http" (default) or "grpc"
    """
    global _tracer_provider

    if not _OTEL_AVAILABLE:
        return

    if _tracer_provider is not None:
        # already initialized
        return

    resource = _build_resource(service_name)

    if exporter.lower() == "grpc":
        span_exporter = OTLPGrpcSpanExporter()
    else:
        # default: HTTP OTLP exporter
        span_exporter = OTLPHttpSpanExporter()

    provider = TracerProvider(resource=resource)
    processor = BatchSpanProcessor(span_exporter)
    provider.add_span_processor(processor)

    trace.set_tracer_provider(provider)
    _tracer_provider = provider


def get_tracer(instrumentation_name: str = "dbop_core.otel_runtime"):
    """
    Helper to get a tracer.

    If init_tracer() was never called or OTEL is unavailable, this still returns
    a tracer (from the global provider), so your code doesn't crash.
    """
    if not _OTEL_AVAILABLE:
        # Fallback to whatever global provider may exist (often a no-op)
        return trace.get_tracer(instrumentation_name)

    if _tracer_provider is None:
        # No explicit provider was set; fallback to global
        return trace.get_tracer(instrumentation_name)

    return _tracer_provider.get_tracer(instrumentation_name)


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def init_metrics(service_name: str = "dbop-core-demo", exporter: str = "http") -> None:
    """
    Initialize a MeterProvider + OTLP metrics exporter.

    :param service_name: logical service name
    :param exporter: "http" (default) or "grpc"
    """
    global _meter_provider

    if not _OTEL_AVAILABLE:
        return

    if _meter_provider is not None:
        # already initialized
        return

    resource = _build_resource(service_name)

    if exporter.lower() == "grpc":
        metric_exporter = OTLPGrpcMetricExporter()
    else:
        # default: HTTP OTLP exporter
        metric_exporter = OTLPHttpMetricExporter()

    reader = PeriodicExportingMetricReader(metric_exporter)
    provider = MeterProvider(resource=resource, metric_readers=[reader])

    metrics.set_meter_provider(provider)
    _meter_provider = provider


def get_meter(instrumentation_name: str = "dbop_core.otel_runtime"):
    """
    Helper to get a meter.

    Returns None if OTEL is not available or metrics are not initialized,
    so callers can simply skip recording metrics in that case.
    """
    if not _OTEL_AVAILABLE or _meter_provider is None:
        return None
    return _meter_provider.get_meter(instrumentation_name)
