from __future__ import annotations
import asyncio
import random
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Tuple, Type, Optional
from contextlib import nullcontext
from .types import AttemptScope, AttemptScopeAsync, PreAttemptFn, TransientClassifier


@dataclass
class RetryPolicy:
    max_retries: int = 5
    initial_delay: float = 0.1
    max_delay: float = 1.0
    jitter: float = 0.2

    def backoff(self) -> Iterable[float]:
        d = self.initial_delay
        for _ in range(self.max_retries):
            j = d * self.jitter
            yield max(0.0, min(self.max_delay, d + random.uniform(-j, j)))
            d = min(self.max_delay, d * 2)


class _NullAsync:
    async def __aenter__(self):
        return None

    async def __aexit__(self, *a):
        return False


async def execute(
    op: Callable[..., Any],
    *,
    args: tuple = (),
    kwargs: dict[str, Any] | None = None,
    retry_on: Tuple[Type[BaseException], ...] = (Exception,),
    classifier: Optional[TransientClassifier] = None,
    raises: bool = True,
    default: Any = None,
    policy: Optional[RetryPolicy] = None,
    attempt_scope: Optional[AttemptScope] = None,
    attempt_scope_async: Optional[AttemptScopeAsync] = None,
    pre_attempt: Optional[PreAttemptFn] = None,
    read_only: bool = False,
    overall_timeout_s: float | None = None,
) -> Any:
    """Agnostic retry executor with optional scopes and classifier."""
    policy = policy or RetryPolicy()
    kwargs = kwargs or {}

    async def _call():
        res = op(*args, **kwargs)
        return await res if asyncio.iscoroutine(res) else res

    async def _once():
        if pre_attempt:
            await pre_attempt()
        return await _call()

    async def _wrapped_once():
        if attempt_scope_async and asyncio.iscoroutinefunction(op):
            async with (
                attempt_scope_async(read_only=read_only) if attempt_scope_async else _NullAsync()
            ):
                return await _once()
        else:
            with attempt_scope(read_only=read_only) if attempt_scope else nullcontext():
                return await _once()

    async def _with_deadline(coro):
        if overall_timeout_s is None:
            return await coro
        return await asyncio.wait_for(coro, timeout=overall_timeout_s)

    for delay in (*policy.backoff(), None):
        try:
            return await _with_deadline(_wrapped_once())
        except retry_on as exc:
            is_transient = classifier(exc) if classifier else True
            if not is_transient or delay is None:
                if raises:
                    raise
                return default
            await asyncio.sleep(delay)
        except Exception:
            if raises:
                raise
            return default
