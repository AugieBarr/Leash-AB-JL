"""Offline demo — the full governed pipeline against Juice Shop WITHOUT the LLM.

Proves the mechanism deterministically and produces a real sealed audit bundle:
open engagement -> scope -> recon -> recruit+scope SQLi specialist -> human
approval -> confirm the injection -> seal the tamper-evident bundle -> verify it.

The live swarm (``python -m swarm.launcher``) narrates this exact flow through a
Band room with the six agents; this script is the no-API-key proof that the
governance + tooling underneath actually works on the real target.

    python scripts/offline_demo.py
"""
from __future__ import annotations

import asyncio
import os
import sys

# Allow `python scripts/offline_demo.py` from anywhere by putting the repo root on the path.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx  # noqa: E402

from agents.agent_tools import reporter_tools  # noqa: E402
from governance.bundle import export_bundle, verify_bundle  # noqa: E402
from governance.capability import ScopeSpec, issue_capability  # noqa: E402
from swarm.engagement import open_engagement  # noqa: E402
from tools.misconfig_tools import misconfig_tools  # noqa: E402
from tools.recon_tools import recon_tools  # noqa: E402
from tools.sqli_tools import sqli_tools  # noqa: E402


def _find(factory, eng, model_name, **kw):
    """Return the (input_model, handler) pair for a tool by its input-model name.
    Extra kwargs are forwarded to the factory (e.g. owner= for cross-specialist scoping)."""
    return next((m, h) for m, h in factory(eng, **kw) if m.__name__ == model_name)


async def _wait_ready(base_url: str, tries: int = 30) -> bool:
    async with httpx.AsyncClient(timeout=5.0) as client:
        for _ in range(tries):
            try:
                if (await client.get(base_url + "/")).status_code < 500:
                    return True
            except Exception:
                pass
            await asyncio.sleep(2)
    return False


async def main() -> int:
    # Start from a clean slate so the demo is idempotent — the ledger replays and
    # *appends* on open, so a stale dir would accumulate events across runs. This
    # dir is gitignored runtime output, regenerated every run.
    import shutil
    from pathlib import Path

    demo_dir = Path("engagements") / "offline-demo"
    if demo_dir.exists():
        shutil.rmtree(demo_dir)

    eng = open_engagement("offline-demo", "localhost", 3000)
    print(f"[*] Engagement {eng.engagement_id} -> {eng.base_url}")
    if not await _wait_ready(eng.base_url):
        print("[!] Juice Shop not reachable on localhost:3000 (docker compose up -d)")
        return 2

    await eng.log("engagement_open", target=f"{eng.target_host}:{eng.target_port}")

    # ScopeWarden issues the recon scout a read-only engagement-wide capability.
    eng.capabilities["leash-recon-scout"] = issue_capability(
        eng.root_cap, ScopeSpec.of(["localhost"], [3000], ["/"])
    )
    print("\n[ScopeWarden] issued recon-scout capability (localhost:3000, /)")

    crawl_model, crawl = _find(recon_tools, eng, "CrawlTargetInput")
    print("\n[Recon Scout] crawl_target:")
    print("  " + (await crawl(crawl_model())).replace("\n", "\n  "))

    # Recon Scout also audits security posture (OWASP A05/A01) under its engagement-wide cap.
    headers_model, headers = _find(misconfig_tools, eng, "SecurityHeadersProbeInput")
    print("\n[Recon Scout] security_headers_probe:")
    print("  " + (await headers(headers_model(path="/"))).replace("\n", "\n  "))

    exposure_model, exposure = _find(misconfig_tools, eng, "ExposureProbeInput")
    print("\n[Recon Scout] exposure_probe:")
    print("  " + (await exposure(exposure_model())).replace("\n", "\n  "))

    # Commander recruits the SQLi specialist; ScopeWarden scopes it to /rest/products only.
    eng.capabilities["leash-sqli-hunter"] = issue_capability(
        eng.root_cap, ScopeSpec.of(["localhost"], [3000], ["/rest/products"])
    )
    print("\n[ScopeWarden] issued sqli-hunter capability (localhost:3000, /rest/products)")

    # Cross-specialist scoping, demonstrated: the SQLi hunter's /rest/products
    # capability fails CLOSED if it reaches for /ftp — the scope guard, not trust.
    sqli_exposure_model, sqli_exposure = _find(
        misconfig_tools, eng, "ExposureProbeInput", owner="leash-sqli-hunter"
    )
    print("\n[Scope guard] SQLi hunter (scoped to /rest/products) attempts exposure_probe:")
    print("  " + await sqli_exposure(sqli_exposure_model()))

    # Human approval gate — the offensive tool now ENFORCES this in code: without a
    # recorded approval it would open the Control Center gate and block. Here the
    # scripted operator pre-approves the exact endpoint so the deterministic demo
    # proceeds without a human; the approval is bound into the signed chain.
    await eng.record_approval("/rest/products/search?q=", operator="demo-operator", tool="manual_sqli_probe")
    print("[Operator] APPROVED (pre-recorded): manual_sqli_probe on /rest/products/search")

    probe_model, probe = _find(sqli_tools, eng, "ManualSqliProbeInput")
    print("\n[SQLi Hunter] manual_sqli_probe:")
    print("  " + await probe(probe_model(path="/rest/products/search?q=")))

    # Auditor seals the bundle; anyone can verify it offline.
    bundle = export_bundle(eng.engagement_id, target="localhost:3000", findings=eng.findings)
    result = verify_bundle(bundle)
    print(f"\n[Auditor] sealed bundle: {bundle}")
    print(f"[Auditor] verify: {result.detail}")
    print(f"[Auditor] findings: {len(eng.findings)} | chain tail {eng.ledger.tail_hash_hex[:16]}…")

    # Reporter writes the deliverable, citing the sealed chain (matches the bundle).
    render_model, render = _find(reporter_tools, eng, "RenderReportInput")
    await render(render_model())
    print(f"[Reporter] wrote {eng.ledger.dir / 'report.md'} ({len(eng.findings)} findings)")

    print(f"\nVerify it yourself:  python -m governance.verify {bundle}")
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
