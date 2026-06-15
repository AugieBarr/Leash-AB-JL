"""Honest scale demonstrations for Leash.

Two artifacts, each measuring exactly one real thing and claiming nothing more:

- ``worker_fanout_bench`` — fans out N worker tool-jobs through Leash's
  ``ConcurrencyCap`` (``swarm/concurrency_cap.py``, the bounded-fan-out primitive
  for the worker tool-job tier); the honest "scales toward 1000" number.
  These are coroutines, **not** live WebSocket agents.
- ``connect_harness`` — opens a real Band WebSocket per registered agent and
  holds them, measuring WS persistence from one host.
"""
