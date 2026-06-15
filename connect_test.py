"""Connectivity canary — confirms band-sdk installs and the registered Band
swarm authenticates over the WebSocket. Connects every agent in agent_config.yaml
concurrently to prove Band allows the whole swarm online at once. Does not need a
working LLM key (Band auth uses each agent's api_key, not the Anthropic key)."""
import asyncio
import os

from dotenv import load_dotenv
from band import Agent
from band.adapters.anthropic import AnthropicAdapter
from band.config import load_agent_config

from swarm.seed import SWARM  # single source of truth for the agent labels


async def connect_one(label: str):
    agent_id, api_key = load_agent_config(label)
    adapter = AnthropicAdapter(model="claude-sonnet-4-5-20250929")
    agent = Agent.create(
        adapter=adapter,
        agent_id=agent_id,
        api_key=api_key,
        ws_url=os.getenv("THENVOI_WS_URL", "wss://app.band.ai/api/v1/socket/websocket"),
        rest_url=os.getenv("THENVOI_REST_URL", "https://app.band.ai/"),
    )
    await agent.start()
    return agent, getattr(agent, "agent_name", "<unknown>")


async def main() -> None:
    load_dotenv()
    os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-placeholder")

    results = await asyncio.gather(*(connect_one(a) for a in SWARM), return_exceptions=True)
    live = []
    for label, r in zip(SWARM, results):
        if isinstance(r, Exception):
            print(f"FAIL {label}: {r!r}")
        else:
            agent, name = r
            live.append(agent)
            print(f"OK   {label} -> {name}")

    print(f"=== {len(live)}/{len(SWARM)} agents connected simultaneously ===")
    for agent in live:
        await agent.stop()


if __name__ == "__main__":
    asyncio.run(main())
