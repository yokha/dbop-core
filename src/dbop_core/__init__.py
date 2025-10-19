from .core import execute, RetryPolicy

__all__ = ["execute", "RetryPolicy"]

# Optional: expose OTEL-integrated helper if available.
try:
    from .otel_runtime import execute_traced_optional  # noqa: F401

    __all__.append("execute_traced_optional")
except Exception:  # pragma: no cover - defensive fallback if OTEL deps are missing/broken
    # If OTEL isn't importable, we just don't expose execute_traced_optional.
    # Core execute/RetryPolicy remain fully usable.
    pass

__version__ = "1.1.0"
