"""Tests for the worker-tier concurrency cap."""
import asyncio

from swarm.concurrency_cap import ConcurrencyCap


async def test_cap_bounds_concurrency():
    cap = ConcurrencyCap(2)
    state = {"current": 0, "peak": 0}

    async def job():
        state["current"] += 1
        state["peak"] = max(state["peak"], state["current"])
        await asyncio.sleep(0.01)
        state["current"] -= 1
        return "done"

    results = await cap.map([job for _ in range(10)])
    assert results == ["done"] * 10
    assert state["peak"] <= 2


async def test_slot_freed_on_exception():
    cap = ConcurrencyCap(1)

    async def boom():
        raise RuntimeError("x")

    async def ok():
        return "ok"

    # If the failed job leaked its slot, this gather would deadlock.
    results = await cap.map([boom, ok])
    assert isinstance(results[0], RuntimeError)
    assert results[1] == "ok"
