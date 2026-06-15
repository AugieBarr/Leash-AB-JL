"""kill_switch — eject the swarm from a Band room (the Band-side kill-switch).

The in-process kill-switch (``Engagement.halt``) hard-stops every offensive tool
the instant it fires — enforced in code, not by asking an agent nicely. This
script is its Band-side complement: it removes every specialist from the case
room so the swarm visibly disbands. Uses the Band agent API keys only (no
Anthropic key needed).

By default the Commander is kept in the room to confirm the kill; pass
``--include-commander`` to clear the room entirely.

    python -m swarm.kill_switch --room <room-id>
    python -m swarm.kill_switch --room <room-id> --include-commander
"""
from __future__ import annotations

import argparse
import asyncio

from dotenv import load_dotenv

from band.client.rest import DEFAULT_REQUEST_OPTIONS
from band.config import load_agent_config

from swarm._band_client import band_client

COMMANDER = "leash-commander"


async def eject_room(room_id: str, *, include_commander: bool = False) -> list[str]:
    """Remove every specialist from the room. Returns the handles/ids removed."""
    load_dotenv()
    cmd_id, cmd_key = load_agent_config(COMMANDER)
    client = band_client(cmd_key)

    resp = await client.agent_api_participants.list_agent_chat_participants(
        room_id, request_options=DEFAULT_REQUEST_OPTIONS
    )
    participants = getattr(resp, "data", resp) or []

    removed: list[str] = []
    for p in participants:
        pid = getattr(p, "id", None)
        handle = getattr(p, "handle", "") or ""
        if not pid:
            continue
        if pid == cmd_id and not include_commander:
            continue  # keep the Commander to confirm the kill
        await client.agent_api_participants.remove_agent_chat_participant(
            room_id, pid, request_options=DEFAULT_REQUEST_OPTIONS
        )
        removed.append(handle or pid)
    return removed


async def _main() -> None:
    parser = argparse.ArgumentParser(description="Eject the Leash swarm from a Band room.")
    parser.add_argument("--room", required=True, help="Room id to eject the swarm from.")
    parser.add_argument(
        "--include-commander", action="store_true", help="Also remove the Commander."
    )
    args = parser.parse_args()
    removed = await eject_room(args.room, include_commander=args.include_commander)
    print(f"Kill-switch: removed {len(removed)} participant(s): {', '.join(removed) or '(none)'}")


if __name__ == "__main__":
    asyncio.run(_main())
