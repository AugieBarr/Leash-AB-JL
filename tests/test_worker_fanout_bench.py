"""Tests for the worker fan-out benchmark.

These assert the safety property the scale story rests on: under heavy fan-out
the ConcurrencyCap is never exceeded and every worker completes.
"""
from scale_test.worker_fanout_bench import run_bench


async def test_cap_is_never_exceeded_under_heavy_fanout():
    r = await run_bench(500, 16, hold_s=0.001)
    assert r.completed == 500
    assert r.errors == 0
    assert r.peak_concurrency <= 16
    assert r.cap_held


async def test_small_cap_serializes_work():
    r = await run_bench(50, 1, hold_s=0.001)
    assert r.completed == 50
    assert r.peak_concurrency == 1  # cap of 1 => fully serial


async def test_peak_can_reach_but_not_exceed_cap():
    # With more workers than the cap and non-trivial work, the cap should be saturated.
    r = await run_bench(200, 8, hold_s=0.005)
    assert r.cap_held
    assert r.peak_concurrency == 8
