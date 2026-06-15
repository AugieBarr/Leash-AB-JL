"""Agent factory + swarm runner.

``build_agent`` wires a Band ``AnthropicAdapter`` (role instructions via
``custom_section`` so Band's platform-tool guidance is preserved) to a set of
role-specific custom tools, then ``Agent.create``. ``run_swarm`` runs the whole
roster in one event loop (proven: 6/6 connect concurrently), so they share the
in-process Engagement while coordinating through Band.
"""
from __future__ import annotations

import asyncio
import os

from band import Agent
from band.adapters.anthropic import AnthropicAdapter
from band.config import load_agent_config

DEFAULT_MODEL = "claude-sonnet-4-5-20250929"


def build_agent(label: str, role_instructions: str, tools: list, *, model: str = DEFAULT_MODEL):
    """Build (but do not start) a Band agent for the given registered label."""
    agent_id, api_key = load_agent_config(label)
    adapter = AnthropicAdapter(
        model=model,
        custom_section=role_instructions,
        additional_tools=tools or None,
        enable_execution_reporting=True,
    )
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
