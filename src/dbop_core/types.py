from __future__ import annotations
from typing import Protocol, Callable, Awaitable
from contextlib import AbstractContextManager, AbstractAsyncContextManager


class AttemptScope(Protocol):
    def __call__(self, *, read_only: bool) -> AbstractContextManager[None]: ...


class AttemptScopeAsync(Protocol):
    def __call__(self, *, read_only: bool) -> AbstractAsyncContextManager[None]: ...


# Called before each attempt (e.g., set per-attempt timeouts)
PreAttemptFn = Callable[[], Awaitable[None]]

# Decide if an exception is transient (should retry)
TransientClassifier = Callable[[BaseException], bool]
