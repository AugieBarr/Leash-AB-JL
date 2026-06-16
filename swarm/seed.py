"""Seed a Band case room for an engagement.

Creates a room (as the Commander), adds the rest of the swarm as participants,
and optionally posts the kickoff message that @mentions the Commander to start.
Uses the Band agent API keys only (no Anthropic key needed to create/seed a room).

For the human-in-the-loop demo the operator can instead create the room in the
Band UI, add the agents, and type the kickoff — that keeps a real human in the
room for the approval gate. This module is the scriptable/headless path.

    python -m swarm.seed --target localhost:3000
    python -m swarm.seed --no-kickoff      # just create the room + add agents
"""
from __future__ import annotations

import argparse
import asyncio

from dotenv import load_dotenv

from band.client.rest import (
    DEFAULT_REQUEST_OPTIONS,
    ChatMessageRequest,
    ChatMessageRequestMentionsItem,
    ChatRoomRequest,
    ParticipantRequest,
)
from band.config import load_agent_config

from swarm._band_client import band_client

SWARM = [
    "leash-commander",
    "leash-scope-warden",
    "leash-auditor",
    "leash-recon-scout",
    "leash-sqli-hunter",
    "leash-xss-hunter",
    "leash-auth-breaker",
    "leash-reporter",
]


def _room_id(room) -> str:
    # REST responses wrap the resource under `.data` (CreateAgentChatResponse.data -> ChatRoom).
    obj = getattr(room, "data", None) or room
    for attr in ("id", "chat_id", "room_id"):
        val = getattr(obj, attr, None)
        if val:
            return val
    raise RuntimeError(f"could not find room id on {room!r}")


# The persistent "brain" tier seeded at room creation. With ``brain_only=True``
# the remaining specialists (recon scout, SQLi hunter, XSS Hunter, Auth Breaker,
# reporter) are NOT seeded —
# the Commander recruits them on discovery, making the tiered recruit-on-discovery
# story a real code path rather than a no-op against a pre-filled room.
BRAIN = {"leash-commander", "leash-scope-warden", "leash-auditor"}


async def seed_room(target: str = "localhost:3000", *, kickoff: bool = True, brain_only: bool = False) -> str:
    load_dotenv()
    creds = {label: load_agent_config(label) for label in SWARM}
    ids = {label: creds[label][0] for label in SWARM}

    commander = band_client(creds["leash-commander"][1])
    room = await commander.agent_api_chats.create_agent_chat(
        chat=ChatRoomRequest(), request_options=DEFAULT_REQUEST_OPTIONS
    )
    room_id = _room_id(room)

    for label in SWARM:
        if label == "leash-commander":
            continue  # the Commander is the room creator/owner
        if brain_only and label not in BRAIN:
            continue  # specialists are recruited live by the Commander
        await commander.agent_api_participants.add_agent_chat_participant(
            chat_id=room_id,
            participant=ParticipantRequest(participant_id=ids[label], role="member"),
            request_options=DEFAULT_REQUEST_OPTIONS,
        )

    if kickoff:
        auditor = band_client(creds["leash-auditor"][1])
        await auditor.agent_api_messages.create_agent_chat_message(
            chat_id=room_id,
            message=ChatMessageRequest(
                content=(
                    f"@leash-commander Begin the authorized engagement against {target} "
                    "(OWASP Juice Shop, deliberately-vulnerable lab target)."
                ),
                mentions=[
                    ChatMessageRequestMentionsItem(
                        id=ids["leash-commander"], handle="leash-commander", name="Leash Commander"
                    )
                ],
            ),
            request_options=DEFAULT_REQUEST_OPTIONS,
        )

    return room_id


async def _main() -> None:
    parser = argparse.ArgumentParser(description="Seed a Band case room for a Leash engagement.")
    parser.add_argument("--target", default="localhost:3000")
    parser.add_argument("--no-kickoff", action="store_true", help="Create the room and add agents, but do not post the kickoff message.")
    parser.add_argument("--brain-only", action="store_true", help="Seed only the brain tier (Commander, ScopeWarden, Auditor); the Commander recruits specialists on discovery.")
    args = parser.parse_args()

    room_id = await seed_room(args.target, kickoff=not args.no_kickoff, brain_only=args.brain_only)
    seeded = len(BRAIN) if args.brain_only else len(SWARM)
    print(f"Seeded room {room_id} with {seeded} agent(s) (target {args.target}; brain_only={args.brain_only}).")
    print("Open it at https://app.band.ai/chat to watch the swarm.")


if __name__ == "__main__":
    asyncio.run(_main())
