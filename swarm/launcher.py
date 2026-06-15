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
    p.add_argument("--resume", action="store_true", help="Continue an existing ledger instead of starting fresh.")
    p.add_argument("--seed", action="store_true", help="Create the Band room (and kickoff) in-process before running, so recruit-on-discovery knows the room id.")
    p.add_argument("--brain-only", action="store_true", help="With --seed, seed only the brain tier; the Commander recruits specialists on discovery.")
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
    if os.getenv("LEASH_ADAPTER", "claude_sdk").lower() == "anthropic" and not os.getenv("ANTHROPIC_API_KEY"):
        # Only the raw-key adapter needs ANTHROPIC_API_KEY. The default claude_sdk
        # adapter drives the swarm on the local Claude subscription with no key, so
        # fail hard here only when the operator explicitly selected the key path.
        raise SystemExit(
            "ERROR: LEASH_ADAPTER=anthropic but ANTHROPIC_API_KEY is not set. Set the "
            "key, or unset LEASH_ADAPTER to run on the local Claude subscription "
            "(claude_sdk adapter — no key needed). Use --boot-check to test connectivity."
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
    # Start each run from a clean ledger so a back-to-back demo does not append to
    # (and inflate) a stale chain. --resume keeps an existing ledger to continue it.
    if not args.resume:
        import shutil
        from pathlib import Path

        eng_dir = Path("engagements") / args.engagement_id  # matches open_engagement's default root
        if eng_dir.exists():
            shutil.rmtree(eng_dir)
    eng = open_engagement(args.engagement_id, args.host, args.port)
    await eng.log("engagement_open", target=f"{args.host}:{args.port}", engagement_id=args.engagement_id)
    if args.seed:
        # Seed the room in-process so the Commander's recruit tool has the room id.
        # --brain-only seeds just the brain tier; the Commander recruits the rest.
        from swarm.seed import seed_room

        eng.band_room_id = await seed_room(f"{args.host}:{args.port}", brain_only=args.brain_only)
        await eng.log("room_seeded", room=eng.band_room_id, brain_only=args.brain_only)
        print(f"Seeded Band room {eng.band_room_id} (brain_only={args.brain_only}).")
    if args.boot_check:
        await _boot_check(eng)
    else:
        await _run(eng)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nshutting down Leash swarm")
