"""Leash swarm launcher.

Opens an engagement (one tamper-evident ledger + root capability), builds the
six agents wired to it, and runs them in one event loop. They wait for the
operator to mention @leash-commander in a Band room to begin.

    python -m swarm.launcher --engagement-id demo-01
    python -m swarm.launcher --boot-check          # connect all 6, then exit
"""
from __future__ import annotations

import argparse
import asyncio
import os

from dotenv import load_dotenv

from agents.base_agent import run_swarm
from agents.roster import build_swarm
from swarm.engagement import open_engagement


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run the Leash governed pentest swarm.")
    p.add_argument("--engagement-id", default="demo-01")
    p.add_argument("--host", default=os.getenv("LEASH_TARGET_HOST", "localhost"))
    p.add_argument("--port", type=int, default=int(os.getenv("LEASH_TARGET_PORT", "3000")))
    p.add_argument("--boot-check", action="store_true", help="Connect all agents, then exit.")
    return p.parse_args()


async def _boot_check(eng) -> None:
    agents = build_swarm(eng)
    online = 0
    for agent in agents:
        await agent.start()
        print(f"  online: {getattr(agent, 'agent_name', '?')}")
        online += 1
    print(f"=== boot-check: {online}/{len(agents)} agents online (engagement {eng.engagement_id}) ===")
    for agent in agents:
        await agent.stop()


async def _run(eng) -> None:
    if not os.getenv("ANTHROPIC_API_KEY"):
        # Fail hard rather than connect and silently stall when the first @mention
        # arrives with no model behind it. (boot-check is exempt — it only connects.)
        raise SystemExit(
            "ERROR: ANTHROPIC_API_KEY is not set. Put it in leash/.env or export it, "
            "then re-run. (Use --boot-check to test connectivity without a key.)"
        )
    agents = build_swarm(eng)
    print(
        f"Leash swarm: {len(agents)} agents online for engagement {eng.engagement_id} "
        f"(target {eng.base_url}). Mention @leash-commander in the room to begin."
    )
    await run_swarm(agents)


async def main() -> None:
    load_dotenv()
    args = _parse_args()
    eng = open_engagement(args.engagement_id, args.host, args.port)
    await eng.log("engagement_open", target=f"{args.host}:{args.port}", engagement_id=args.engagement_id)
    if args.boot_check:
        await _boot_check(eng)
    else:
        await _run(eng)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nshutting down Leash swarm")
