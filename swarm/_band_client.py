"""Shared Band REST client construction.

The ``AsyncRestClient`` must point at the configured REST URL — the SDK default
is a dev URL — so both the room seeder and the Band-side kill-switch build their
clients the same way. Keeping it here makes a URL/env-var change one edit, not
two. Importing this pulls in the Band SDK, so only the Band-touching modules
(``seed``, ``kill_switch``) use it; the offline governance path stays SDK-free.
"""
from __future__ import annotations

import os

from band.client.rest import (
    DEFAULT_REQUEST_OPTIONS,
    AsyncRestClient,
    ChatMessageRequest,
)
from band.config import load_agent_config


def rest_base_url() -> str:
    return os.getenv("THENVOI_REST_URL", "https://app.band.ai/").rstrip("/")


def band_client(api_key: str) -> AsyncRestClient:
    return AsyncRestClient(base_url=rest_base_url(), api_key=api_key)


async def post_governance_signal(eng, text: str, *, agent: str = "leash-auditor") -> None:
    """Post a governance signal (audit seal, capability grant, kill-switch) into the
    engagement's Band room as a *code-dispatched* message — not an LLM ``@mention``.

    This is what makes the room transcript itself a governance artifact: the signal
    lands in Band deterministically as a consequence of the governed action, so these
    signals are demonstrably lost if Band drops. That is the honest proof that Band is
    the load-bearing coordination/broadcast plane — distinct from the in-process
    enforcement substrate, which keeps working regardless.

    No-op when the engagement is not bound to a room (offline runs and tests), so the
    governance-only import surface stays Band-SDK-free until a live room exists.
    """
    if not eng.band_room_id:
        return
    client = band_client(load_agent_config(agent)[1])
    await client.agent_api_messages.create_agent_chat_message(
        chat_id=eng.band_room_id,
        message=ChatMessageRequest(content=text),
        request_options=DEFAULT_REQUEST_OPTIONS,
    )
