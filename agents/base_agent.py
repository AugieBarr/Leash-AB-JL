"""Agent factory + swarm runner.

``build_agent`` wires a Band adapter (role instructions via ``custom_section``
so Band's platform-tool guidance is preserved) to a set of role-specific custom
tools, then ``Agent.create``. The adapter is chosen by ``LEASH_ADAPTER``:

  * ``claude_sdk`` (default) — drives the swarm on the operator's local Claude
    subscription via the ``claude`` binary; needs **no** ``ANTHROPIC_API_KEY``.
  * ``anthropic`` — uses a raw Anthropic API key (``ANTHROPIC_API_KEY``).

``run_swarm`` runs the whole roster in one event loop (6/6 connect concurrently),
so they share the in-process Engagement while coordinating through Band.
"""
from __future__ import annotations

import asyncio
import os

from band import Agent
from band.adapters.anthropic import AnthropicAdapter
from band.adapters.claude_sdk import ClaudeSDKAdapter
from band.config import load_agent_config
from band.core.types import AdapterFeatures, Emit

DEFAULT_MODEL = "claude-sonnet-4-5-20250929"

# Surface each tool_call / tool_result (and the agent's thoughts) into the Band
# room so the human operator watches the swarm act in real time — the modern
# replacement for the deprecated ``enable_execution_reporting`` flag.
_REPORTING = AdapterFeatures(emit=frozenset({Emit.EXECUTION, Emit.THOUGHTS}))


def _build_adapter(role_instructions: str, tools: list, model: str | None):
    """Select the LLM adapter. Default is the Claude-subscription path (no API
    key); ``LEASH_ADAPTER=anthropic`` switches to a raw Anthropic key."""
    if os.getenv("LEASH_ADAPTER", "claude_sdk").lower() == "anthropic":
        return AnthropicAdapter(
            model=model or DEFAULT_MODEL,
            custom_section=role_instructions,
            additional_tools=tools or None,
            enable_execution_reporting=True,
        )
    # ``model=None`` lets ClaudeSDKAdapter pin its own auth-safe default, avoiding
    # the legacy request shape the ``claude`` binary rejects under some auth modes.
    return ClaudeSDKAdapter(
        model=model,
        custom_section=role_instructions,
        additional_tools=tools or None,
        features=_REPORTING,
    )


def build_agent(label: str, role_instructions: str, tools: list, *, model: str | None = None):
    """Build (but do not start) a Band agent for the given registered label."""
    agent_id, api_key = load_agent_config(label)
    adapter = _build_adapter(role_instructions, tools, model)
    return Agent.create(
        adapter=adapter,
        agent_id=agent_id,
        api_key=api_key,
        ws_url=os.getenv("THENVOI_WS_URL", "wss://app.band.ai/api/v1/socket/websocket"),
        rest_url=os.getenv("THENVOI_REST_URL", "https://app.band.ai/"),
    )


async def run_swarm(agents: list) -> None:
    """Run every agent forever in this event loop. ``return_exceptions=True`` so
    one agent crashing does not cancel the whole swarm — the failure is logged
    and the surviving agents keep serving the room (mirrors the resilience the
    connect harness and concurrency cap already use)."""
    results = await asyncio.gather(*(agent.run() for agent in agents), return_exceptions=True)
    for agent, res in zip(agents, results):
        if isinstance(res, BaseException):
            name = getattr(agent, "agent_name", agent)
            print(f"[leash] agent {name} exited with error: {res!r}")
