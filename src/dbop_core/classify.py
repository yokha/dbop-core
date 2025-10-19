from __future__ import annotations


def dbapi_classifier(exc: BaseException) -> bool:
    msg = str(exc).lower()

    # ---- PostgreSQL ----
    pg = (
        getattr(exc, "pgcode", None)
        or getattr(exc, "sqlstate", None)
        or getattr(getattr(exc, "orig", None), "pgcode", None)
    )
    if pg in {"40P01", "55P03", "40001"}:
        return True
    if "canceling statement due to statement timeout" in msg:
        return True
    if "deadlock detected" in msg or "canceling statement due to lock timeout" in msg:
        return True

    # ---- MySQL / MariaDB ----
    errno = None
    orig = getattr(exc, "orig", None)
    try:
        if orig and getattr(orig, "args", None):
            errno = int(orig.args[0])
    except Exception:
        pass
    if errno is None:
        try:
            if getattr(exc, "args", None):
                errno = int(exc.args[0])
        except Exception:
            pass

    # 1213=deadlock, 1205=lock wait, 3572=NOWAIT, 2006/2013=conn hiccups
    if errno in {1213, 1205, 3572, 2006, 2013}:
        return True
    if "nowait is set" in msg or "deadlock" in msg or "lock wait timeout" in msg:
        return True

    # ---- SQLite ----
    if "database is locked" in msg:
        return True

    # ---- Generic op/timeout-ish ----
    names = [type(exc).__name__, type(orig).__name__ if orig else ""]
    if any(n in {"OperationalError", "InterfaceError", "TimeoutError"} for n in names):
        if any(
            t in msg
            for t in [
                "timeout",
                "deadlock",
                "lock wait",
                "gone away",
                "lost connection",
                "connection reset",
            ]
        ):
            return True

    return False
