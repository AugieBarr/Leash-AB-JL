"""Tests for the ScopeWarden and Auditor custom tools (agents/agent_tools.py).

These cover the governance tools the live swarm calls — issuing/checking
capabilities and sealing/verifying the chain — without any Band or LLM.
"""
from agents.agent_tools import auditor_tools, commander_tools, scope_warden_tools
from swarm.engagement import open_engagement


def _pair(factory, eng, name):
    return next((m, h) for m, h in factory(eng) if m.__name__ == name)


async def test_issue_capability_stores_and_logs(tmp_path):
    eng = open_engagement("t-warden", "localhost", 3000, root=str(tmp_path))
    model, handler = _pair(scope_warden_tools, eng, "IssueCapabilityInput")
    out = await handler(model(agent_label="leash-sqli-hunter", paths=["/rest/products"]))
    assert "Issued" in out
    assert "leash-sqli-hunter" in eng.capabilities
    assert "capability_issued" in (eng.ledger.dir / "audit.ndjson").read_text()


async def test_check_capability_permitted_and_denied(tmp_path):
    eng = open_engagement("t-warden2", "localhost", 3000, root=str(tmp_path))
    issue_m, issue_h = _pair(scope_warden_tools, eng, "IssueCapabilityInput")
    await issue_h(issue_m(agent_label="leash-sqli-hunter", paths=["/rest/products"]))

    check_m, check_h = _pair(scope_warden_tools, eng, "CheckCapabilityInput")
    permitted = await check_h(check_m(agent_label="leash-sqli-hunter", url="http://localhost:3000/rest/products/search"))
    denied = await check_h(check_m(agent_label="leash-sqli-hunter", url="http://localhost:3000/rest/admin"))
    assert "PERMITTED" in permitted
    assert "DENIED" in denied


async def test_auditor_append_verify_and_seal(tmp_path):
    eng = open_engagement("t-aud", "localhost", 3000, root=str(tmp_path))
    await eng.log("engagement_open", target="localhost:3000")

    append_m, append_h = _pair(auditor_tools, eng, "AppendEventInput")
    assert "Recorded event" in await append_h(append_m(kind="milestone", summary="recon complete"))

    verify_m, verify_h = _pair(auditor_tools, eng, "VerifyChainInput")
    assert "Chain OK" in await verify_h(verify_m())

    seal_m, seal_h = _pair(auditor_tools, eng, "SealBundleInput")
    sealed = await seal_h(seal_m())
    assert "Sealed bundle" in sealed
    assert (eng.ledger.dir / "t-aud_bundle.tar.gz").exists()
