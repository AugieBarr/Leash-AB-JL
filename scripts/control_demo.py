"""Control-center demo — the governed pipeline with a LIVE, web-driven human gate.

This is ``offline_demo`` with the approval gate handed to the browser instead of
hard-coded. It runs the real governed flow against Juice Shop — recon, misconfig
probes, capability scoping — and then BLOCKS at the SQLi gate until the operator
clicks APPROVE or HALT in the Control Center. A background ``watch_halt`` makes
the KILL SWITCH live the whole time, not just at the gate.

It is the no-API-key proof that the Control Center actually drives a running
engagement: the same control channel serves the live Band swarm.

    # terminal 1 — the operable viewer
    python -m viewer.viewer --engagement control-demo
    # terminal 2 — the paced engagement
    python scripts/control_demo.py
    # then open http://localhost:8089/?engagement=control-demo and hit APPROVE / HALT
"""
from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import sys
from pathlib import Path

# Allow `python scripts/control_demo.py` from anywhere.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx  # noqa: E402

from agents.agent_tools import reporter_tools  # noqa: E402
from governance.bundle import export_bundle, verify_bundle  # noqa: E402
from governance.capability import ScopeSpec, issue_capability  # noqa: E402
from swarm.control_channel import await_decision, request_approval, watch_halt  # noqa: E402
from swarm.engagement import open_engagement  # noqa: E402
from tools.misconfig_tools import misconfig_tools  # noqa: E402
from tools.recon_tools import recon_tools  # noqa: E402
from tools.sqli_tools import sqli_tools  # noqa: E402

ENGAGEMENT = "control-demo"


def _find(factory, eng, model_name, **kw):
    """Return the (input_model, handler) pair for a tool by its input-model name."""
    return next((m, h) for m, h in factory(eng, **kw) if m.__name__ == model_name)


async def _wait_ready(base_url: str, tries: int = 15) -> bool:
    async with httpx.AsyncClient(timeout=5.0) as client:
        for _ in range(tries):
            try:
                if (await client.get(base_url + "/")).status_code < 500:
                    return True
            except Exception:
                pass
            await asyncio.sleep(1)
    return False


async def main() -> int:
    p = argparse.ArgumentParser(description="Control-center demo with a web-driven approval gate.")
    p.add_argument("--pace", type=float, default=1.6, help="Seconds between beats so the stream is watchable.")
    p.add_argument("--gate-timeout", type=float, default=600.0, help="How long to wait for the operator's decision.")
    args = p.parse_args()
    pace = args.pace

    # Clean slate so the demo is idempotent (the ledger appends on open).
    demo_dir = Path("engagements") / ENGAGEMENT
    if demo_dir.exists():
        shutil.rmtree(demo_dir)

    eng = open_engagement(ENGAGEMENT, "localhost", 3000)
    print(f"[*] Engagement {eng.engagement_id} -> {eng.base_url}")
    if not await _wait_ready(eng.base_url):
        print("[!] Juice Shop not reachable on localhost:3000 (docker compose up -d juice-shop)")
        return 2

    print("\n    Open the Control Center:  http://localhost:8089/?engagement=" + ENGAGEMENT)
    print("    Watch recon stream in, then APPROVE or HALT at the gate (KILL SWITCH is live throughout).\n")

    # The kill-switch watcher runs for the whole engagement, so the operator can
    # stop it at any beat — not only at the approval gate.
    halt_task = asyncio.create_task(watch_halt(eng))
    try:
        await eng.log("engagement_open", target=f"{eng.target_host}:{eng.target_port}", engagement_id=eng.engagement_id)
        await asyncio.sleep(pace)

        # ScopeWarden grants the recon scout an engagement-wide read-only capability.
        eng.capabilities["leash-recon-scout"] = issue_capability(
            eng.root_cap, ScopeSpec.of(["localhost"], [3000], ["/"]), agent_id="leash-recon-scout"
        )
        await eng.log("capability_issued", agent="leash-recon-scout", paths=["/"])
        print("[ScopeWarden] issued recon-scout capability (localhost:3000, /)")
        await asyncio.sleep(pace)

        if eng.halted:
            return await _finish(eng)

        # Recon — real read-only probes against the live target.
        crawl_model, crawl = _find(recon_tools, eng, "CrawlTargetInput")
        print("[Recon Scout] crawl_target …")
        await crawl(crawl_model())
        await asyncio.sleep(pace)

        headers_model, headers = _find(misconfig_tools, eng, "SecurityHeadersProbeInput")
        print("[Recon Scout] security_headers_probe …")
        await headers(headers_model(path="/"))
        await asyncio.sleep(pace)

        exposure_model, exposure = _find(misconfig_tools, eng, "ExposureProbeInput")
        print("[Recon Scout] exposure_probe …")
        await exposure(exposure_model())
        await asyncio.sleep(pace)

        if eng.halted:
            return await _finish(eng)

        # ScopeWarden scopes the SQLi hunter to /rest/products only.
        eng.capabilities["leash-sqli-hunter"] = issue_capability(
            eng.root_cap, ScopeSpec.of(["localhost"], [3000], ["/rest/products"]), agent_id="leash-sqli-hunter"
        )
        await eng.log("capability_issued", agent="leash-sqli-hunter", paths=["/rest/products"])
        print("[ScopeWarden] issued sqli-hunter capability (localhost:3000, /rest/products)")
        await asyncio.sleep(pace)

        probe_model, probe = _find(sqli_tools, eng, "ManualSqliProbeInput")

        # The leash holds. Scoped to /rest/products, the SQLi hunter reaches for
        # /ftp — and the fail-closed scope guard refuses it before any request is
        # sent. The refusal is recorded as a governed event (the Defenses panel).
        print("[SQLi Hunter] manual_sqli_probe /ftp  (out of scope) …")
        print("  " + (await probe(probe_model(path="/ftp"))))
        await asyncio.sleep(pace)

        if eng.halted:
            return await _finish(eng)

        # THE GATE — block on the operator's browser decision.
        endpoint = "/rest/products/search?q="
        gate = await request_approval(eng, tool="manual_sqli_probe", endpoint=endpoint,
                                      detail="UNION-based SQL injection probe on the product search parameter")
        print(f"\n[GATE OPEN] waiting for operator decision in the Control Center (gate {gate}) …")
        decision = await await_decision(eng, gate, timeout=args.gate_timeout)
        print(f"[GATE] operator decision: {decision.upper()}")

        if decision != "approve":
            if not eng.halted:
                await eng.halt("operator halted at approval gate")
            return await _finish(eng)

        # Record the governed approval (the sole writer logs it into the chain),
        # then run the now-authorized, in-scope probe.
        await eng.log("approval", action="manual_sqli_probe", decision="approved",
                      operator="operator", gate_id=gate)
        print("[SQLi Hunter] manual_sqli_probe …")
        print("  " + (await probe(probe_model(path=endpoint))).replace("\n", "\n  "))
        await asyncio.sleep(pace)

        return await _finish(eng)
    finally:
        # Await the cancel so a halt landing at the same instant finishes its
        # in-flight ledger write (eng.halt → eng.log) before we tear down, rather
        # than dropping the kill_switch event mid-append.
        halt_task.cancel()
        try:
            await halt_task
        except (asyncio.CancelledError, Exception):
            pass  # teardown must never mask the engagement's own return/seal


async def _finish(eng) -> int:
    """Seal the bundle and render the report — runs on every exit path (approved,
    halted, or stopped), so the chain always ends sealed and verifiable."""
    await asyncio.sleep(0.2)
    bundle = export_bundle(eng.engagement_id, target=f"{eng.target_host}:{eng.target_port}", findings=eng.findings)
    result = verify_bundle(bundle)
    render_model, render = _find(reporter_tools, eng, "RenderReportInput")
    await render(render_model())
    status = "HALTED" if eng.halted else "completed"
    print(f"\n[Auditor] sealed {bundle.name} — {result.detail}")
    print(f"[Engagement] {status} | {len(eng.findings)} findings | chain tail {eng.ledger.tail_hash_hex[:16]}…")
    print(f"Verify it yourself:  python -m governance.verify {bundle}")
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
