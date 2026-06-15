# Scale tests — what the numbers actually mean

Leash's headline mentions scaling toward **1000 agents**. This directory backs
that claim *honestly*: two small harnesses, each measuring exactly one real
thing and claiming nothing it didn't measure.

| Harness | Command | Proves | Does **not** prove |
|---|---|---|---|
| `worker_fanout_bench` | `--workers 1000 --cap 16` | The worker tool-job tier fans out 1000 jobs through the `ConcurrencyCap` without ever exceeding the cap, and every job completes | 1000 jobs ≠ 1000 live WebSocket agents — these are coroutines |
| `worker_fanout_bench` | `--workers 200 --target http://localhost:3000` | The fan-out + `scope_guard` hold under load against the real target | Same caveat — coroutines, not agents |
| `connect_harness` | `--hold N` | Band holds one persistent WebSocket per **registered** agent, from one host, for the full duration | The number connected = agents you registered (6 here), not 30 and not 1000 |

## Measured (this build, 2026-06-14)

```
worker_fanout_bench --workers 1000 --cap 16
    peak concurrency : 16  (cap 16) -> OK, cap held
    completed/errors : 1000/0 of 1000
    wall / throughput: 0.77s  /  ~1,305 jobs/s

worker_fanout_bench --workers 200 --cap 16 --target http://localhost:3000
    peak concurrency : 16  (cap 16) -> OK, cap held   (real scope-guarded GETs)
    completed/errors : 200/0 of 200
    wall / throughput: 0.38s  /  ~525 jobs/s

connect_harness --hold 3
    [6/6] WebSockets open — held 3s, closed cleanly
```

## The honest framing

> The worker layer scales toward 1000 concurrent **tasks** by distributing across
> machines — demonstrated here with a 1000-job fan-out under a hard concurrency
> cap, plus 200 real scope-guarded probes against the live target. The live
> **agent** layer is the registered Band agents (six in this build), each on a
> persistent WebSocket. Full 1000-*agent* WebSocket scale needs Band's enterprise
> tier; the architecture is unchanged — only the agent count and the WS quota move.

The safety property the cap guarantees (`peak_concurrency <= cap`, with a slot
freed by *task death*, not explicit release) is unit-tested in
[`tests/test_worker_fanout_bench.py`](../tests/test_worker_fanout_bench.py) and
[`tests/test_concurrency_cap.py`](../tests/test_concurrency_cap.py).
