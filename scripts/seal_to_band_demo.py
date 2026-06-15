"""The 'seal lands in Band' beat — deterministic, ~10 seconds, no live LLM swarm.

Seeds a Band room (brain tier), records a short representative governed chain, and
calls the Auditor's ``seal_bundle`` tool — which seals the tamper-evident bundle
AND posts the chain-tail hash into the room as a code-dispatched event. Open the
room and watch the ``AUDIT SEALED — …`` message appear, posted by the Auditor.

This is the demo's closing beat: the proof does not just land on disk, it lands in
Band. Keyless of Anthropic — it uses only the Band agent API keys in
``agent_config.yaml`` (no ANTHROPIC_API_KEY, no Claude subscription burn), so it is
fast and repeatable for recording.

    python scripts/seal_to_band_demo.py
    # then open the printed room at https://app.band.ai/chat and watch the seal land
"""
from __future__ import annotations

import asyncio
import os
import shutil
import sys
from pathlib import Path

# Allow `python scripts/seal_to_band_demo.py` from anywhere.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv  # noqa: E402

from agents.agent_tools import auditor_tools  # noqa: E402
from governance.capability import ScopeSpec, issue_capability  # noqa: E402
from swarm.engagement import open_engagement  # noqa: E402
from swarm.seed import seed_room  # noqa: E402

ENGAGEMENT = "seal-band-demo"


async def main() -> int:
    load_dotenv()

    demo_dir = Path("engagements") / ENGAGEMENT
    if demo_dir.exists():
        shutil.rmtree(demo_dir)  # idempotent: a fresh chain each run

    # Seed a room with just the brain tier (Commander, ScopeWarden, Auditor) and no
    # kickoff @mention — we only need a room the Auditor can post the seal into.
    room_id = await seed_room("localhost:3000", kickoff=False, brain_only=True)
    eng = open_engagement(ENGAGEMENT, "localhost", 3000)
    eng.band_room_id = room_id
    print(f"[*] Seeded room {room_id}")
    print("    Open it now:  https://app.band.ai/chat")

    # A short, representative governed chain so the sealed bundle is non-trivial.
    await eng.log("engagement_open", target="localhost:3000", engagement_id=ENGAGEMENT)
    eng.capabilities["leash-sqli-hunter"] = issue_capability(
        eng.root_cap,
        ScopeSpec.of(["localhost"], [3000], ["/rest/products"]),
        agent_id="leash-sqli-hunter",
    )
    await eng.log("capability_issued", agent="leash-sqli-hunter", paths=["/rest/products"])
    await eng.log("approval", action="manual_sqli_probe", decision="approved", operator="operator")
    await eng.log(
        "tool_result", tool="manual_sqli_probe", path="/rest/products/search?q=", injectable=True
    )
    eng.record_finding(
        type="sqli",
        endpoint="/rest/products/search",
        severity="high",
        evidence="single-quote injection -> HTTP 500",
    )

    # The Auditor seals the bundle AND posts the chain-tail hash into the room.
    seal_model, seal = next(
        (m, h) for m, h in auditor_tools(eng) if m.__name__ == "SealBundleInput"
    )
    print("\n[Auditor] " + await seal(seal_model()))
    print("\n[*] Switch to the room — an 'AUDIT SEALED — …' message just posted from the Auditor.")
    print(
        f"    Verify the same bundle offline:  "
        f"python -m governance.verify engagements/{ENGAGEMENT}/{ENGAGEMENT}_bundle.tar.gz"
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
