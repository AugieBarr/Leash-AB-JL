"""Bounded concurrent execution for the worker tool-job tier.

Port of PolisCodeDispatch.BackgroundAgent.ConcurrencyCap: a hard ceiling on
concurrent jobs where a slot is freed by the *completion* of the job (success,
error, or cancellation) via ``add_done_callback`` — never by an explicit release,
so a crashed/cancelled worker always frees its slot.
"""
from __future__ import annotations

import asyncio
from typing import Awaitable, Callable


class ConcurrencyCap:
    def __init__(self, cap: int) -> None:
        if cap < 1:
            raise ValueError("cap must be >= 1")
        self.cap = cap
        self._sem = asyncio.Semaphore(cap)

    async def run(self, factory: Callable[[], Awaitable]):
        """Acquire a slot, run the coroutine produced by ``factory``, and free the
        slot when it finishes regardless of outcome."""
        await self._sem.acquire()
        try:
            coro = factory()  # may raise *synchronously* before producing a coroutine
        except BaseException:
            self._sem.release()  # …in which case free the slot we just took
            raise
        task = asyncio.ensure_future(coro)
        task.add_done_callback(lambda _t: self._sem.release())
        return await task

    async def map(self, factories: list[Callable[[], Awaitable]]) -> list:
        """Run all factories under the cap. Exceptions are returned, not raised."""
        return await asyncio.gather(
            *(self.run(f) for f in factories), return_exceptions=True
        )
