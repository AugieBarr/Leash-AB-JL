"""worker_fanout_bench — the honest "scales toward 1000" measurement.

The worker tool-job tier is plain asyncio tasks (NOT Band agents), bounded by
the same ``ConcurrencyCap`` the swarm uses in production. This benchmark fans
out ``--workers`` jobs through ``ConcurrencyCap(--cap)``, proves peak concurrency
never exceeds the cap (the slot-freed-by-task-death invariant), and reports
throughput.

With ``--target`` each job issues a **real** scope-guarded ``httpx`` GET (proving
the fan-out + ``scope_guard`` hold under load); without it each job is a fixed
async sleep — a pure measurement of the fan-out machinery.

These are coroutines, **not** 1000 live WebSocket agents — stated plainly. Full
1000-agent WS scale needs Band's enterprise tier; the architecture is unchanged.

    python -m scale_test.worker_fanout_bench --workers 1000 --cap 16
    python -m scale_test.worker_fanout_bench --workers 200 --cap 16 --target http://localhost:3000
"""
from __future__ import annotations

import argparse
import asyncio
import time
from dataclasses import dataclass
from typing import Callable, Optional

from swarm.concurrency_cap import ConcurrencyCap


@dataclass
class BenchResult:
    workers: int
    cap: int
    peak_concurrency: int
    completed: int
    errors: int
    wall_seconds: float

    @property
    def throughput(self) -> float:
        return self.completed / self.wall_seconds if self.wall_seconds else 0.0

    @property
    def cap_held(self) -> bool:
        """The core safety property: the cap was never exceeded."""
        return self.peak_concurrency <= self.cap


class _Tracker:
    """Counts live jobs; records the high-water mark."""

    def __init__(self) -> None:
        self.current = 0
        self.peak = 0

    def enter(self) -> None:
        self.current += 1
        if self.current > self.peak:
            self.peak = self.current

    def exit(self) -> None:
        self.current -= 1


def _sleep_job(tracker: _Tracker, hold_s: float) -> Callable[[], "asyncio.Future"]:
    async def job():
        tracker.enter()
        try:
            await asyncio.sleep(hold_s)
            return True
        finally:
            tracker.exit()

    return job


def _probe_job(tracker: _Tracker, client, url: str, capability) -> Callable[[], "asyncio.Future"]:
    from governance.scope_guard import scope_guard

    async def job():
        tracker.enter()
        try:
            scope_guard(url, capability)  # fail-closed: off-target raises before any request
            resp = await client.get(url)
            return resp.status_code < 500
        finally:
            tracker.exit()

    return job


async def run_bench(
    workers: int,
    cap_size: int,
    *,
    hold_s: float = 0.01,
    target: Optional[str] = None,
) -> BenchResult:
    tracker = _Tracker()
    cap = ConcurrencyCap(cap_size)

    if target:
        import httpx
        from urllib.parse import urlsplit

        from governance.capability import ScopeSpec, root_capability

        parts = urlsplit(target)
        host = parts.hostname or "localhost"
        port = parts.port or (443 if parts.scheme == "https" else 80)
        capability = root_capability("scale-bench", ScopeSpec.of([host], [port], ["/"]))
        async with httpx.AsyncClient(timeout=10.0) as client:
            jobs = [_probe_job(tracker, client, target, capability) for _ in range(workers)]
            t0 = time.perf_counter()
            results = await cap.map(jobs)
            wall = time.perf_counter() - t0
    else:
        jobs = [_sleep_job(tracker, hold_s) for _ in range(workers)]
        t0 = time.perf_counter()
        results = await cap.map(jobs)
        wall = time.perf_counter() - t0

    completed = sum(1 for r in results if not isinstance(r, BaseException))
    errors = sum(1 for r in results if isinstance(r, BaseException))
    return BenchResult(workers, cap_size, tracker.peak, completed, errors, wall)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Fan-out worker benchmark for the Leash worker tier.")
    p.add_argument("--workers", type=int, default=1000)
    p.add_argument("--cap", type=int, default=16, help="Max concurrent jobs (the ConcurrencyCap size).")
    p.add_argument("--hold-ms", type=float, default=10.0, help="Per-job sleep in sleep-mode (no --target).")
    p.add_argument("--target", default=None, help="If set, each job is a real scope-guarded httpx GET to this URL.")
    return p.parse_args()


async def _main() -> int:
    args = _parse_args()
    print(f"[*] fan-out: {args.workers} workers, cap {args.cap}"
          + (f", real probes -> {args.target}" if args.target else f", sleep {args.hold_ms:.0f}ms"))
    r = await run_bench(args.workers, args.cap, hold_s=args.hold_ms / 1000.0, target=args.target)
    print(f"    peak concurrency : {r.peak_concurrency}  (cap {r.cap}) -> "
          + ("OK, cap held" if r.cap_held else "VIOLATED"))
    print(f"    completed/errors : {r.completed}/{r.errors} of {r.workers}")
    print(f"    wall / throughput: {r.wall_seconds:.2f}s  /  {r.throughput:,.0f} jobs/s")
    # Fail loudly if the cap was breached or any worker leaked an exception.
    return 0 if (r.cap_held and r.errors == 0 and r.completed == r.workers) else 1


if __name__ == "__main__":
    import sys

    sys.exit(asyncio.run(_main()))
