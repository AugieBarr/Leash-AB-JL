"""Tests for the Reporter — the final pentest report artifact.

A real report must roll findings up by severity, embed the audit attestation
(chain tail, public key, verify command), and be written to disk.
"""
from agents.agent_tools import reporter_tools
from swarm.engagement import open_engagement


def _pair(factory, eng, name):
    return next((m, h) for m, h in factory(eng) if m.__name__ == name)


async def test_report_has_summary_findings_and_attestation(tmp_path):
    eng = open_engagement("t-report", "localhost", 3000, root=str(tmp_path))
    await eng.log("engagement_open", target="localhost:3000")
    eng.record_finding(type="security_misconfiguration", endpoint="/", severity="medium", evidence="missing CSP")
    eng.record_finding(type="sqli", endpoint="/rest/products/search", severity="high", evidence="HTTP 500 on quote")

    model, handler = _pair(reporter_tools, eng, "RenderReportInput")
    report = await handler(model())

    assert "# Leash Pentest Report" in report
    assert "## Executive summary" in report
    assert "## Audit attestation" in report
    # Severity rollup is ordered high before medium.
    assert "1 high, 1 medium" in report
    assert report.index("| high |") < report.index("| medium |")  # high listed first
    assert "python -m governance.verify" in report
    assert (eng.ledger.dir / "report.md").exists()


async def test_report_handles_no_findings(tmp_path):
    eng = open_engagement("t-report-empty", "localhost", 3000, root=str(tmp_path))
    model, handler = _pair(reporter_tools, eng, "RenderReportInput")
    report = await handler(model())
    assert "No findings recorded" in report
    assert "## Audit attestation" in report


async def test_report_marks_halted_engagement(tmp_path):
    eng = open_engagement("t-report-halt", "localhost", 3000, root=str(tmp_path))
    await eng.halt("operator halt")
    model, handler = _pair(reporter_tools, eng, "RenderReportInput")
    report = await handler(model())
    assert "HALTED by kill-switch" in report
