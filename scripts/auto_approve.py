"""Auto-approve every human gate in a running engagement — a RECORDING / TEST aid.

The human approval gate is the product: in a real run an operator clicks APPROVE
or HALT in the Control Center. This script stands in for that operator during an
UNATTENDED capture — e.g. recording the full live Band arc with no one at the
keyboard — by submitting an APPROVE for each gate as it opens.

It is deliberately NOT a flag on the launcher: the gate bypass stays an explicit,
external act, never baked into the core swarm. And every approval it submits is
recorded with operator="auto-approve (unattended)", so the tamper-evident chain
never claims a human approved when one did not.

    python scripts/auto_approve.py <engagement-id> [--delay 2.0]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

# Allow `python scripts/auto_approve.py` from anywhere.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from swarm.control_channel import submit_decision  # noqa: E402

OPERATOR = "auto-approve (unattended)"


async def auto_approve(
    engagement_id: str,
    *,
    root: str = "engagements",
    delay: float = 2.0,
    poll: float = 0.5,
    rounds: int = 600,
) -> list[str]:
    """Watch the engagement ledger and APPROVE each gate as it opens, recording the
    approval under an explicit auto-approve operator so the chain stays honest.
    Returns the gate ids approved."""
    ledger = Path(root) / engagement_id / "audit.ndjson"
    approved: list[str] = []
    for _ in range(rounds):
        if ledger.exists():
            for line in ledger.read_text(encoding="utf-8").splitlines():
                try:
                    rec = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                if rec.get("kind") != "approval_requested":
                    continue
                gate_id = json.loads(rec["payload"]).get("gate_id")
                if gate_id and gate_id not in approved:
                    await asyncio.sleep(delay)  # let the gate beat read on camera
                    submit_decision(
                        engagement_id,
                        action="approve",
                        gate_id=gate_id,
                        operator=OPERATOR,
                        root=root,
                    )
                    approved.append(gate_id)
                    print(f"[auto-approve] approved {gate_id}", flush=True)
        await asyncio.sleep(poll)
    return approved


def _main() -> None:
    p = argparse.ArgumentParser(
        description="Auto-approve gates for an unattended Leash capture (recording/test aid)."
    )
    p.add_argument("engagement_id")
    p.add_argument("--root", default="engagements")
    p.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Seconds to wait before approving each gate (so the beat reads on camera).",
    )
    args = p.parse_args()
    asyncio.run(auto_approve(args.engagement_id, root=args.root, delay=args.delay))


if __name__ == "__main__":
    _main()
