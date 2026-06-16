"""Tests for the Auth Breaker — the third offensive specialist.

The probe must (1) confirm a bypass only when the injection yields a token where
the baseline is rejected, (2) report honest true-negatives when the login is
hardened or authenticates loosely, and (3) be governed like the other offensive
tools: refused when halted, blocked behind the approval gate, bounded by the
scope guard. Deterministic — a fake httpx client stands in for a live target.
"""
import json

import httpx

from governance.capability import ScopeSpec, issue_capability
from swarm.engagement import open_engagement
from tools.auth_tools import auth_tools


def _pair(eng, name, **kw):
    return next((m, h) for m, h in auth_tools(eng, **kw) if m.__name__ == name)


def _scope(eng, paths):
    eng.capabilities["leash-auth-breaker"] = issue_capability(
        eng.root_cap, ScopeSpec.of(["localhost"], [3000], paths)
    )


class _FakeResp:
    def __init__(self, status, body):
        self.status_code = status
        if isinstance(body, dict):
            self._data = body
            self.text = json.dumps(body)
        else:
            self._data = None
            self.text = body

    def json(self):
        if self._data is None:
            raise ValueError("not json")
        return self._data


class _FakeClient:
    """Stand-in for httpx.AsyncClient. ``_responder(email) -> _FakeResp`` is set
    per-test, so baseline vs injection POSTs can return different responses."""

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, json=None):
        return type(self)._responder((json or {}).get("email", ""))


def _client(responder):
    return type("_C", (_FakeClient,), {"_responder": staticmethod(responder)})


_TOKEN = {"authentication": {"token": "eyJhbGciOi.LEASH.demo", "umail": "x"}}
_REJECT = {"error": "Invalid email or password."}


async def test_confirms_auth_bypass(tmp_path, monkeypatch):
    eng = open_engagement("t-auth-ok", "localhost", 3000, root=str(tmp_path))
    _scope(eng, ["/rest/user"])
    await eng.record_approval("/rest/user/login", operator="op", tool="manual_auth_bypass_probe")
    # Injection yields a token; the baseline credential is rejected -> confirmed.
    monkeypatch.setattr(
        httpx, "AsyncClient",
        _client(lambda email: _FakeResp(200, _TOKEN) if "OR 1=1" in email else _FakeResp(401, _REJECT)),
    )

    model, handler = _pair(eng, "ManualAuthBypassProbeInput", gate_timeout=0.1)
    out = await handler(model(path="/rest/user/login"))
    assert "VULNERABLE" in out and "A07" in out
    assert len(eng.findings) == 1 and eng.findings[0]["severity"] == "critical"
    assert not eng.halted
    assert eng.ledger.verify_chain().ok


async def test_hardened_login_not_confirmed(tmp_path, monkeypatch):
    eng = open_engagement("t-auth-hard", "localhost", 3000, root=str(tmp_path))
    _scope(eng, ["/rest/user"])
    await eng.record_approval("/rest/user/login", operator="op", tool="manual_auth_bypass_probe")
    # Both attempts rejected -> no bypass.
    monkeypatch.setattr(httpx, "AsyncClient", _client(lambda email: _FakeResp(401, _REJECT)))

    model, handler = _pair(eng, "ManualAuthBypassProbeInput", gate_timeout=0.1)
    out = await handler(model(path="/rest/user/login"))
    assert "not confirmed" in out and "no auth bypass" in out
    assert eng.findings == []


async def test_loose_login_not_attributable(tmp_path, monkeypatch):
    eng = open_engagement("t-auth-loose", "localhost", 3000, root=str(tmp_path))
    _scope(eng, ["/rest/user"])
    await eng.record_approval("/rest/user/login", operator="op", tool="manual_auth_bypass_probe")
    # Both yield a token -> can't attribute the bypass to the injection.
    monkeypatch.setattr(httpx, "AsyncClient", _client(lambda email: _FakeResp(200, _TOKEN)))

    model, handler = _pair(eng, "ManualAuthBypassProbeInput", gate_timeout=0.1)
    out = await handler(model(path="/rest/user/login"))
    assert "not confirmed" in out and "can't be attributed" in out
    assert eng.findings == []


async def test_blocked_out_of_scope(tmp_path):
    eng = open_engagement("t-auth-scope", "localhost", 3000, root=str(tmp_path))
    _scope(eng, ["/rest/products"])  # not /rest/user -> the login endpoint is out of scope
    await eng.record_approval("/rest/user/login", operator="op", tool="manual_auth_bypass_probe")
    model, handler = _pair(eng, "ManualAuthBypassProbeInput", gate_timeout=0.1)
    out = await handler(model(path="/rest/user/login"))
    assert "BLOCKED by scope guard" in out
    assert eng.findings == []


async def test_refuses_when_halted(tmp_path):
    eng = open_engagement("t-auth-halt", "localhost", 3000, root=str(tmp_path))
    _scope(eng, ["/rest/user"])
    await eng.halt("operator kill-switch")
    model, handler = _pair(eng, "ManualAuthBypassProbeInput", gate_timeout=0.1)
    out = await handler(model(path="/rest/user/login"))
    assert "HALTED" in out
    assert eng.findings == []


async def test_refuses_without_approval(tmp_path):
    eng = open_engagement("t-auth-gate", "localhost", 3000, root=str(tmp_path))
    _scope(eng, ["/rest/user"])
    model, handler = _pair(eng, "ManualAuthBypassProbeInput", gate_timeout=0.1, gate_poll=0.02)
    out = await handler(model(path="/rest/user/login"))
    assert "BLOCKED" in out
    assert eng.halted and eng.findings == []
    assert "approval_requested" in (eng.ledger.dir / "audit.ndjson").read_text()
    assert eng.ledger.verify_chain().ok
