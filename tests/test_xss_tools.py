"""Tests for the XSS Hunter — the second offensive specialist.

The probe must (1) confirm reflected XSS only when the marked payload comes back
unescaped in an HTML context, (2) report honest true-negatives when it is escaped
or returned in a non-HTML body, and (3) be governed exactly like the SQLi tools:
refused when halted, blocked behind the approval gate, and bounded by the scope
guard. All deterministic — a fake httpx client stands in for a live target.
"""
import httpx

from governance.capability import ScopeSpec, issue_capability
from swarm.engagement import open_engagement
from tools.xss_tools import _PAYLOAD, xss_tools


def _pair(eng, name, **kw):
    return next((m, h) for m, h in xss_tools(eng, **kw) if m.__name__ == name)


def _scope(eng, paths):
    eng.capabilities["leash-xss-hunter"] = issue_capability(
        eng.root_cap, ScopeSpec.of(["localhost"], [3000], paths)
    )


class _FakeResp:
    def __init__(self, status, text, content_type="text/html; charset=utf-8"):
        self.status_code = status
        self.text = text
        self.headers = {"content-type": content_type}


class _FakeClient:
    """Stand-in for httpx.AsyncClient. ``_body``/``_ctype`` are set per-test as
    class attributes so the handler's internally-constructed client sees them."""

    _body = ""
    _ctype = "text/html; charset=utf-8"

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url):
        return _FakeResp(200, type(self)._body, type(self)._ctype)


def _client_returning(body, ctype="text/html; charset=utf-8"):
    return type("_C", (_FakeClient,), {"_body": body, "_ctype": ctype})


async def test_confirms_reflected_xss(tmp_path, monkeypatch):
    eng = open_engagement("t-xss-ok", "localhost", 3000, root=str(tmp_path))
    _scope(eng, ["/rest/products"])
    await eng.record_approval("/rest/products/search?q=", operator="op", tool="manual_xss_probe")
    # Payload reflected verbatim (unescaped) in an HTML response → confirmed.
    monkeypatch.setattr(httpx, "AsyncClient", _client_returning(f"<p>no results for {_PAYLOAD}</p>"))

    model, handler = _pair(eng, "ManualXssProbeInput", gate_timeout=0.1)
    out = await handler(model(path="/rest/products/search?q="))
    assert "VULNERABLE" in out
    assert len(eng.findings) == 1 and eng.findings[0]["type"] == "xss"
    assert not eng.halted
    assert eng.ledger.verify_chain().ok


async def test_escaped_reflection_not_confirmed(tmp_path, monkeypatch):
    eng = open_engagement("t-xss-esc", "localhost", 3000, root=str(tmp_path))
    _scope(eng, ["/rest/products"])
    await eng.record_approval("/rest/products/search?q=", operator="op", tool="manual_xss_probe")
    escaped = _PAYLOAD.replace("<", "&lt;").replace(">", "&gt;")
    monkeypatch.setattr(httpx, "AsyncClient", _client_returning(f"<p>{escaped}</p>"))

    model, handler = _pair(eng, "ManualXssProbeInput", gate_timeout=0.1)
    out = await handler(model(path="/rest/products/search?q="))
    assert "not confirmed" in out and "escaped" in out
    assert eng.findings == []


async def test_non_html_context_not_confirmed(tmp_path, monkeypatch):
    eng = open_engagement("t-xss-json", "localhost", 3000, root=str(tmp_path))
    _scope(eng, ["/rest/products"])
    await eng.record_approval("/rest/products/search?q=", operator="op", tool="manual_xss_probe")
    # Reflected unescaped, but the body is JSON — not a directly-exploitable XSS.
    monkeypatch.setattr(
        httpx, "AsyncClient",
        _client_returning(f'{{"q":"{_PAYLOAD}"}}', ctype="application/json"),
    )

    model, handler = _pair(eng, "ManualXssProbeInput", gate_timeout=0.1)
    out = await handler(model(path="/rest/products/search?q="))
    assert "not confirmed" in out and "application/json" in out
    assert eng.findings == []


async def test_blocked_out_of_scope(tmp_path):
    eng = open_engagement("t-xss-scope", "localhost", 3000, root=str(tmp_path))
    _scope(eng, ["/rest/products"])
    # Approve the out-of-scope endpoint so the gate passes — the scope guard must
    # still fail closed (capability, not approval, is the boundary here).
    await eng.record_approval("/admin", operator="op", tool="manual_xss_probe")
    model, handler = _pair(eng, "ManualXssProbeInput", gate_timeout=0.1)
    out = await handler(model(path="/admin?x="))
    assert "BLOCKED by scope guard" in out
    assert eng.findings == []


async def test_refuses_when_halted(tmp_path):
    eng = open_engagement("t-xss-halt", "localhost", 3000, root=str(tmp_path))
    _scope(eng, ["/rest/products"])
    await eng.halt("operator kill-switch")
    model, handler = _pair(eng, "ManualXssProbeInput", gate_timeout=0.1)
    out = await handler(model(path="/rest/products/search?q="))
    assert "HALTED" in out
    assert eng.findings == []


async def test_refuses_without_approval(tmp_path):
    eng = open_engagement("t-xss-gate", "localhost", 3000, root=str(tmp_path))
    _scope(eng, ["/rest/products"])
    # No operator decision; tiny timeout → the gate fails closed before any request.
    model, handler = _pair(eng, "ManualXssProbeInput", gate_timeout=0.1, gate_poll=0.02)
    out = await handler(model(path="/rest/products/search?q="))
    assert "BLOCKED" in out
    assert eng.halted and eng.findings == []
    assert "approval_requested" in (eng.ledger.dir / "audit.ndjson").read_text()
    assert eng.ledger.verify_chain().ok
