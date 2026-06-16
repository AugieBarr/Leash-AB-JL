"""Tests for the Data Exposure Sentinel — a governed DLP / PII-PHI test specialist.

It must (1) confirm only when a sensitive pattern is present, reporting the TYPE
and COUNT but never the raw value; (2) report an honest not-confirmed on a clean
response; and (3) be governed like the other offensive tools — refused when
halted, blocked behind the approval gate, bounded by the scope guard. All
deterministic with a fake httpx client.
"""
import httpx

from governance.capability import ScopeSpec, issue_capability
from swarm.engagement import open_engagement
from tools.exposure_tools import exposure_tools


def _pair(eng, name, **kw):
    return next((m, h) for m, h in exposure_tools(eng, **kw) if m.__name__ == name)


def _scope(eng, paths):
    eng.capabilities["leash-data-sentinel"] = issue_capability(
        eng.root_cap, ScopeSpec.of(["localhost"], [3000], paths)
    )


class _FakeResp:
    def __init__(self, status, text):
        self.status_code = status
        self.text = text


class _FakeClient:
    _body = ""

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url):
        return _FakeResp(200, type(self)._body)


def _client_returning(body):
    return type("_C", (_FakeClient,), {"_body": body})


async def test_confirms_and_redacts_exposure(tmp_path, monkeypatch):
    eng = open_engagement("t-exp-ok", "localhost", 3000, root=str(tmp_path))
    _scope(eng, ["/rest/user"])
    await eng.record_approval("/rest/user/whoami", operator="op", tool="manual_data_exposure_probe")
    secret = "patient jane.doe@example.com SSN 123-45-6789"
    monkeypatch.setattr(httpx, "AsyncClient", _client_returning(secret))

    model, handler = _pair(eng, "ManualDataExposureProbeInput", gate_timeout=0.1)
    out = await handler(model(path="/rest/user/whoami"))
    assert "VULNERABLE" in out
    assert "email" in out and "us_ssn" in out
    # responsible: the raw sensitive values must NOT appear in the tool output…
    assert "jane.doe@example.com" not in out
    assert "123-45-6789" not in out
    # …nor in the audit chain on disk.
    chain = (eng.ledger.dir / "audit.ndjson").read_text()
    assert "jane.doe@example.com" not in chain and "123-45-6789" not in chain
    assert len(eng.findings) == 1 and eng.findings[0]["type"] == "sensitive_data_exposure"
    assert eng.ledger.verify_chain().ok


async def test_clean_response_not_confirmed(tmp_path, monkeypatch):
    eng = open_engagement("t-exp-clean", "localhost", 3000, root=str(tmp_path))
    _scope(eng, ["/rest/user"])
    await eng.record_approval("/rest/user/whoami", operator="op", tool="manual_data_exposure_probe")
    monkeypatch.setattr(httpx, "AsyncClient", _client_returning('{"status":"ok"}'))
    model, handler = _pair(eng, "ManualDataExposureProbeInput", gate_timeout=0.1)
    out = await handler(model(path="/rest/user/whoami"))
    assert "not confirmed" in out
    assert eng.findings == []


async def test_blocked_out_of_scope(tmp_path):
    eng = open_engagement("t-exp-scope", "localhost", 3000, root=str(tmp_path))
    _scope(eng, ["/rest/products"])
    await eng.record_approval("/admin", operator="op", tool="manual_data_exposure_probe")
    model, handler = _pair(eng, "ManualDataExposureProbeInput", gate_timeout=0.1)
    out = await handler(model(path="/admin"))
    assert "BLOCKED by scope guard" in out
    assert eng.findings == []


async def test_refuses_when_halted(tmp_path):
    eng = open_engagement("t-exp-halt", "localhost", 3000, root=str(tmp_path))
    _scope(eng, ["/rest/user"])
    await eng.halt("operator kill-switch")
    model, handler = _pair(eng, "ManualDataExposureProbeInput", gate_timeout=0.1)
    out = await handler(model(path="/rest/user/whoami"))
    assert "HALTED" in out
    assert eng.findings == []


async def test_refuses_without_approval(tmp_path):
    eng = open_engagement("t-exp-gate", "localhost", 3000, root=str(tmp_path))
    _scope(eng, ["/rest/user"])
    model, handler = _pair(eng, "ManualDataExposureProbeInput", gate_timeout=0.1, gate_poll=0.02)
    out = await handler(model(path="/rest/user/whoami"))
    assert "BLOCKED" in out
    assert eng.halted and eng.findings == []
    assert "approval_requested" in (eng.ledger.dir / "audit.ndjson").read_text()
    assert eng.ledger.verify_chain().ok
