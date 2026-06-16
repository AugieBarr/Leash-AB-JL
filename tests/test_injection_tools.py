"""Tests for the Prompt-Injection Tester — a governed AI-era test specialist.

It must (1) confirm injection only when the endpoint emits the directive's canary
token, (2) report an honest not-confirmed otherwise, and (3) be governed like the
other offensive tools — refused when halted, blocked behind the approval gate,
bounded by the scope guard. Deterministic with a fake httpx client.
"""
import httpx

from governance.capability import ScopeSpec, issue_capability
from swarm.engagement import open_engagement
from tools.injection_tools import _CANARY, injection_tools


def _pair(eng, name, **kw):
    return next((m, h) for m, h in injection_tools(eng, **kw) if m.__name__ == name)


def _scope(eng, paths):
    eng.capabilities["leash-injection-tester"] = issue_capability(
        eng.root_cap, ScopeSpec.of(["localhost"], [3000], paths)
    )


class _FakeResp:
    def __init__(self, status, text):
        self.status_code = status
        self.text = text


class _FakeClient:
    """No-op stand-in for httpx.AsyncClient (mirrors test_xss_tools.py)."""

    _body = ""

    def __init__(self, *a, **k):
        self._noop = True

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url):
        return _FakeResp(200, type(self)._body)


def _client_returning(body):
    return type("_C", (_FakeClient,), {"_body": body})


async def test_confirms_prompt_injection(tmp_path, monkeypatch):
    eng = open_engagement("t-inj-ok", "localhost", 3000, root=str(tmp_path))
    _scope(eng, ["/rest/chatbot"])
    await eng.record_approval("/rest/chatbot/respond", operator="op", tool="manual_prompt_injection_probe")
    # The endpoint followed the injected directive and echoed the canary → confirmed.
    monkeypatch.setattr(httpx, "AsyncClient", _client_returning(f"Sure! {_CANARY}"))
    model, handler = _pair(eng, "ManualPromptInjectionProbeInput", gate_timeout=0.1)
    out = await handler(model(path="/rest/chatbot/respond?query="))
    assert "VULNERABLE" in out
    assert len(eng.findings) == 1 and eng.findings[0]["type"] == "prompt_injection"
    assert eng.ledger.verify_chain().ok


async def test_no_canary_not_confirmed(tmp_path, monkeypatch):
    eng = open_engagement("t-inj-no", "localhost", 3000, root=str(tmp_path))
    _scope(eng, ["/rest/chatbot"])
    await eng.record_approval("/rest/chatbot/respond", operator="op", tool="manual_prompt_injection_probe")
    monkeypatch.setattr(httpx, "AsyncClient", _client_returning("I can't help with that."))
    model, handler = _pair(eng, "ManualPromptInjectionProbeInput", gate_timeout=0.1)
    out = await handler(model(path="/rest/chatbot/respond?query="))
    assert "not confirmed" in out
    assert eng.findings == []


async def test_blocked_out_of_scope(tmp_path):
    eng = open_engagement("t-inj-scope", "localhost", 3000, root=str(tmp_path))
    _scope(eng, ["/rest/chatbot"])
    await eng.record_approval("/admin", operator="op", tool="manual_prompt_injection_probe")
    model, handler = _pair(eng, "ManualPromptInjectionProbeInput", gate_timeout=0.1)
    out = await handler(model(path="/admin?query="))
    assert "BLOCKED by scope guard" in out
    assert eng.findings == []


async def test_refuses_when_halted(tmp_path):
    eng = open_engagement("t-inj-halt", "localhost", 3000, root=str(tmp_path))
    _scope(eng, ["/rest/chatbot"])
    await eng.halt("operator kill-switch")
    model, handler = _pair(eng, "ManualPromptInjectionProbeInput", gate_timeout=0.1)
    out = await handler(model(path="/rest/chatbot/respond?query="))
    assert "HALTED" in out
    assert eng.findings == []


async def test_refuses_without_approval(tmp_path):
    eng = open_engagement("t-inj-gate", "localhost", 3000, root=str(tmp_path))
    _scope(eng, ["/rest/chatbot"])
    model, handler = _pair(eng, "ManualPromptInjectionProbeInput", gate_timeout=0.1, gate_poll=0.02)
    out = await handler(model(path="/rest/chatbot/respond?query="))
    assert "BLOCKED" in out
    assert eng.halted and eng.findings == []
    assert "approval_requested" in (eng.ledger.dir / "audit.ndjson").read_text()
    assert eng.ledger.verify_chain().ok
