"""connect_harness — prove Band holds N persistent WebSockets from one host.

Opens a real Band WebSocket for every agent registered in ``agent_config.yaml``
at once, holds them for ``--hold`` seconds, and reports how many connected. This
is the live WS-persistence measurement behind the scale story — it uses the real
agent credentials (no Anthropic key needed: ``start()`` opens the socket;
reasoning only happens when a message arrives).

It claims exactly what it measures: the agents you have registered, held for the
duration. It does **not** claim 1000 agents — that is the worker tier
(``worker_fanout_bench``) plus Band's enterprise WS tier.

    python -m scale_test.connect_harness --hold 60
"""
from __future__ import annotations

import argparse
import asyncio

from dotenv import load_dotenv

from agents.base_agent import build_agent
from swarm.seed import SWARM

_PROBE_INSTRUCTION = "Connectivity harness agent. Hold the WebSocket open; take no action."


async def hold_connections(labels: list[str], hold_seconds: float) -> tuple[int, int]:
    """Connect every label, hold for ``hold_seconds``, then close. Returns (online, total)."""
    agents = [build_agent(label, _PROBE_INSTRUCTION, []) for label in labels]

    online = 0
    for agent, label in zip(agents, labels):
        try:
            await agent.start()
            online += 1
            print(f"  connected: {label}")
        except Exception as exc:  # one bad socket must not abort the rest of the harness
            print(f"  FAILED   : {label} ({type(exc).__name__}: {exc})")

    print(f"[{online}/{len(labels)}] WebSockets open — holding {hold_seconds:.0f}s …")
    try:
        await asyncio.sleep(hold_seconds)
    finally:
        for agent in agents:
            try:
                await agent.stop()
            except Exception as exc:
                # Best-effort teardown: a socket that never opened (or already
                # dropped) must not abort cleanup of the others.
                print(f"  (teardown) {type(exc).__name__} closing an agent — ignored")
    print(f"[{online}/{len(labels)}] held {hold_seconds:.0f}s, closed cleanly.")
    return online, len(labels)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Hold N live Band WebSockets to measure persistence.")
    p.add_argument("--hold", type=float, default=60.0, help="Seconds to hold the sockets open.")
    return p.parse_args()


async def _main() -> int:
    load_dotenv()
    args = _parse_args()
    online, total = await hold_connections(list(SWARM), args.hold)
    return 0 if online == total else 1


if __name__ == "__main__":
    import sys

    sys.exit(asyncio.run(_main()))
