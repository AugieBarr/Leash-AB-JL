"""Connectivity canary — confirms band-sdk installs and a registered Band agent
authenticates over the WebSocket. Does not require a working LLM key (the Band
auth uses the agent api_key, not the Anthropic key)."""
import asyncio
import os

from dotenv import load_dotenv
from band import Agent
from band.adapters.anthropic import AnthropicAdapter
from band.config import load_agent_config


async def main() -> None:
    load_dotenv()
    # Placeholder so adapter construction never blocks; unused for a pure connect test.
    os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-placeholder")

    agent_id, api_key = load_agent_config("leash-auditor")
    adapter = AnthropicAdapter(model="claude-sonnet-4-5-20250929")
    agent = Agent.create(
        adapter=adapter,
        agent_id=agent_id,
        api_key=api_key,
        ws_url=os.getenv("THENVOI_WS_URL", "wss://app.band.ai/api/v1/socket/websocket"),
        rest_url=os.getenv("THENVOI_REST_URL", "https://app.band.ai/"),
    )

    await agent.start()
    print("CONNECTED as:", getattr(agent, "agent_name", "<unknown>"))
    await agent.stop()
    print("DISCONNECTED cleanly")


if __name__ == "__main__":
    asyncio.run(main())
