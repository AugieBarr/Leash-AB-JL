"""Tests for the kill-switch — the in-process hard stop on offensive tools.

The kill-switch is not a polite request: once ``eng.halt()`` fires, every
target-touching tool must refuse, the refusal must be audited, and no finding
may be manufactured. These tests assert that contract deterministically.
"""
from agents.agent_tools import commander_tools
from swarm.engagement import open_engagement
from tools.misconfig_tools import misconfig_tools
from tools.recon_tools import recon_tools
from tools.sqli_tools import sqli_tools


def _pair(factory, eng, name):
    return next((m, h) for m, h in factory(eng) if m.__name__ == name)


async def test_commander_tool_engages_halt(tmp_path):
    eng = open_engagement("t-ks-cmd", "localhost", 3000, root=str(tmp_path))
    model, handler = _pair(commander_tools, eng, "IssueKillSwitchInput")
    out = await handler(model(reason="operator said halt"))
    assert eng.halted
    assert "KILL-SWITCH ENGAGED" in out


async def test_halt_blocks_every_offensive_tool(tmp_path):
    eng = open_engagement("t-ks-block", "localhost", 3000, root=str(tmp_path))
    await eng.halt("operator said halt")
    assert eng.halted

    gated = [
        (sqli_tools, "ManualSqliProbeInput", {}),
        (sqli_tools, "RunSqlmapInput", {"path": "/rest/products/search?q=apple"}),
        (recon_tools, "HttpProbeInput", {}),
        (recon_tools, "CrawlTargetInput", {}),
        (misconfig_tools, "SecurityHeadersProbeInput", {}),
        (misconfig_tools, "ExposureProbeInput", {}),
    ]
    for factory, name, kwargs in gated:
        model, handler = _pair(factory, eng, name)
        out = await handler(model(**kwargs))
        assert "HALTED" in out, f"{name} ran after kill-switch"
    # A halt must never let a finding through.
    assert eng.findings == []


async def test_halt_and_refusals_are_audited(tmp_path):
    eng = open_engagement("t-ks-audit", "localhost", 3000, root=str(tmp_path))
    await eng.halt("kill")
    model, handler = _pair(sqli_tools, eng, "ManualSqliProbeInput")
    await handler(model())  # one refused attempt

    text = (eng.ledger.dir / "audit.ndjson").read_text()
    assert "kill_switch" in text
    assert "blocked_halted" in text
    # The chain stays valid across the halt + refusal events.
    assert eng.ledger.verify_chain().ok


async def test_halt_refusals_across_all_tools_stay_chain_verified(tmp_path):
    """After the kill-switch refuses every offensive tool, the chain of all those
    refusals must still verify end to end — the halt produces a tamper-evident
    record, not merely a stop."""
    eng = open_engagement("t-ks-chain", "localhost", 3000, root=str(tmp_path))
    await eng.halt("operator said halt")

    gated = [
        (sqli_tools, "ManualSqliProbeInput", {}),
        (sqli_tools, "RunSqlmapInput", {"path": "/rest/products/search?q=apple"}),
        (recon_tools, "HttpProbeInput", {}),
        (recon_tools, "CrawlTargetInput", {}),
        (misconfig_tools, "SecurityHeadersProbeInput", {}),
        (misconfig_tools, "ExposureProbeInput", {}),
    ]
    for factory, name, kwargs in gated:
        model, handler = _pair(factory, eng, name)
        out = await handler(model(**kwargs))
        assert "HALTED" in out, f"{name} ran after kill-switch"

    assert eng.findings == []
    result = eng.ledger.verify_chain()
    assert result.ok, result.detail
    # One blocked_halted event was chained per refused tool.
    text = (eng.ledger.dir / "audit.ndjson").read_text()
    assert text.count('"blocked_halted"') == len(gated)
