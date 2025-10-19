from __future__ import annotations
from dbop_core.core import RetryPolicy


def test_backoff_increases_and_caps(monkeypatch):
    # make jitter deterministic: always return 0 offset
    monkeypatch.setattr("random.uniform", lambda a, b: 0.0)
    p = RetryPolicy(max_retries=5, initial_delay=0.1, max_delay=0.5, jitter=0.2)
    delays = list(p.backoff())
    # exact sequence with zero jitter: 0.1, 0.2, 0.4, 0.5, 0.5
    assert delays == [0.1, 0.2, 0.4, 0.5, 0.5]
    # non-decreasing and capped
    assert all(d >= 0 for d in delays)
    assert all(d <= 0.5 for d in delays)
    assert sorted(delays) == delays
