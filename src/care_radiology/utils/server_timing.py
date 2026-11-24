"""
Per-request step timings, sent back in the `Server-Timing` response header so the browser's network panel shows
where a request spends its time. `ServerTimingMixin` starts a collection for each request of a viewset when
CARE_RADIOLOGY_SERVER_TIMING_ENABLED is on; `timed()` records one step into it and does nothing outside one.
"""

import contextvars
import time
from contextlib import contextmanager

from django.db import connection

_entries = contextvars.ContextVar("care_radiology_server_timing", default=None)


class _Entry:
    __slots__ = ("desc", "dur", "name")

    def __init__(self, name, desc):
        self.name = name
        self.desc = desc
        self.dur = None


@contextmanager
def timed(name, desc=None):
    """Records the time spent in the block as one step. Steps are listed in the order they start."""
    entries = _entries.get()
    if entries is None:
        yield
        return
    entry = _Entry(name, desc)
    entries.append(entry)
    started = time.perf_counter()
    try:
        yield
    finally:
        entry.dur = (time.perf_counter() - started) * 1000


@contextmanager
def collect():
    """Collects the steps of a request, along with the count and total time of its database queries."""
    entries = []
    db = {"count": 0, "ms": 0.0}

    def db_wrapper(execute, sql, params, many, context):
        started = time.perf_counter()
        try:
            return execute(sql, params, many, context)
        finally:
            db["count"] += 1
            db["ms"] += (time.perf_counter() - started) * 1000

    token = _entries.set(entries)
    try:
        with connection.execute_wrapper(db_wrapper):
            yield entries, db
    finally:
        _entries.reset(token)


def header_value(entries, db, total_ms):
    """The `Server-Timing` header value. A step that ran more than once gets a numbered name for each run."""
    seen = {}
    metrics = [f'total;dur={total_ms:.2f};desc="view total"']
    metrics.append(f'db;dur={db["ms"]:.2f};desc="{db["count"]} queries (all steps)"')
    for entry in entries:
        if entry.dur is None:
            continue
        seen[entry.name] = seen.get(entry.name, 0) + 1
        name = entry.name if seen[entry.name] == 1 else f"{entry.name}-{seen[entry.name]}"
        metric = f"{name};dur={entry.dur:.2f}"
        if entry.desc:
            metric += f';desc="{entry.desc}"'
        metrics.append(metric)
    return ", ".join(metrics)
