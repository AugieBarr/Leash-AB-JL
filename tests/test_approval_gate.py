"""Tests for the code-enforced human approval gate.

The differentiator's hardest claim is "safe to run unsupervised": an offensive
tool must not exploit on the agent's say-so alone. These tests assert the gate is
enforced in *code* — the tool refuses without a real operator approval, the gate
fails safe to halt, and an approval is bound into the tamper-evident chain — not
merely requested by a prompt.
"""
import asyncio

from swarm.control_channel import enforce_gate, submit_decision
from swarm.engagement import open_engagement
from tools.sqli_tools import sqli_tools


def _pair(factory, eng, name, **kw):
    return next((m, h) for m, h in factory(eng, **kw) if m.__name__ == name)


async def _wait_for_gate(eng, tries: int = 300) -> None:
    """Spin until the gate has opened (``approval_requested`` is on the chain), so
    a decision is submitted only after ``request_approval`` cleared any stale one."""
    audit = eng.ledger.dir / "audit.ndjson"
    for _ in range(tries):
        if audit.exists() and "approval_requested" in audit.read_text():
            return
        await asyncio.sleep(0.01)


# ----- approval bookkeeping --------------------------------------------------
def test_approval_key_normalizes(tmp_path):
    eng = open_engagement("t-key", "localhost", 3000, root=str(tmp_path))
    # Query string, sqlmap '*' markers and '..' traversal all collapse to one key,
    # so an approval can't be dodged by decorating the path the tool was approved for.
    assert eng.approval_key("/rest/products/search?q=") == "/rest/products/search"
    assert eng.approval_key("/rest/products/search?q=*") == "/rest/products/search"
    assert eng.approval_key("/rest/products/../products/search") == "/rest/products/search"


async def test_record_approval_marks_and_logs(tmp_path):
    eng = open_engagement("t-rec", "localhost", 3000, root=str(tmp_path))
    assert not eng.is_approved("/rest/products/search?q=")
    await eng.record_approval("/rest/products/search?q=", operator="josh", tool="manual_sqli_probe")
    assert eng.is_approved("/rest/products/search")  # same normalized key
    text = (eng.ledger.dir / "audit.ndjson").read_text()
    assert '"approval"' in text and "josh" in text
    assert eng.ledger.verify_chain().ok


# ----- enforce_gate ----------------------------------------------------------
async def test_enforce_gate_approve_records_and_passes(tmp_path):
    eng = open_engagement("t-eg-ok", "localhost", 3000, root=str(tmp_path))
    task = asyncio.create_task(
        enforce_gate(eng, tool="manual_sqli_probe", endpoint="/rest/products/search?q=",
                     poll=0.02, timeout=3.0)
    )
    await _wait_for_gate(eng)
    submit_decision("t-eg-ok", action="approve", gate_id="gate-0", root=str(tmp_path))
    assert await task is True
    assert eng.is_approved("/rest/products/search") and not eng.halted
    assert eng.ledger.verify_chain().ok


async def test_enforce_gate_times_out_to_halt(tmp_path):
    eng = open_engagement("t-eg-to", "localhost", 3000, root=str(tmp_path))
    # No decision ever lands — the gate must never default open.
    ok = await enforce_gate(eng, tool="run_sqlmap", endpoint="/rest/products", poll=0.02, timeout=0.12)
    assert ok is False and eng.halted
    assert eng.ledger.verify_chain().ok


async def test_enforce_gate_halt_decision_fails_closed(tmp_path):
    eng = open_engagement("t-eg-halt", "localhost", 3000, root=str(tmp_path))
    task = asyncio.create_task(
        enforce_gate(eng, tool="manual_sqli_probe", endpoint="/rest/products/search?q=",
                     poll=0.02, timeout=3.0)
    )
    await _wait_for_gate(eng)
    submit_decision("t-eg-halt", action="halt", root=str(tmp_path))
    assert await task is False and eng.halted
    assert eng.ledger.verify_chain().ok


# ----- the offensive tool enforces the gate ---------------------------------
async def test_tool_refuses_without_approval(tmp_path):
    eng = open_engagement("t-gate-block", "localhost", 3000, root=str(tmp_path))
    model, handler = _pair(sqli_tools, eng, "ManualSqliProbeInput", gate_timeout=0.1, gate_poll=0.02)
    # No operator decision → the tool must refuse, halt, and exploit nothing. It
    # returns at the gate, before any network call, so no live target is needed.
    out = await handler(model(path="/rest/products/search?q="))
    assert "BLOCKED" in out
    assert eng.halted
    assert eng.findings == []
    text = (eng.ledger.dir / "audit.ndjson").read_text()
    assert "approval_requested" in text  # the gate was actually opened
    assert eng.ledger.verify_chain().ok


class _FakeResp:
    def __init__(self, status: int, text: str) -> None:
        self.status_code = status
        self.text = text


class _FakeClient:
    """Stand-in for httpx.AsyncClient so the approved-path test exercises the gate
    short-circuit without needing a live Juice Shop."""

    def __init__(self, *a, **k) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url: str):
        injectable = url.endswith("apple'")
        return _FakeResp(500 if injectable else 200, "SQL syntax error" if injectable else "ok")


async def test_pre_approved_tool_skips_gate_and_runs(tmp_path, monkeypatch):
    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)
    eng = open_engagement("t-gate-pre", "localhost", 3000, root=str(tmp_path))
    await eng.record_approval("/rest/products/search?q=", operator="op", tool="manual_sqli_probe")

    model, handler = _pair(sqli_tools, eng, "ManualSqliProbeInput", gate_timeout=0.1)
    out = await handler(model(path="/rest/products/search?q="))
    assert "VULNERABLE" in out
    assert len(eng.findings) == 1 and not eng.halted
    # Already approved → the tool must NOT re-open a gate.
    assert "approval_requested" not in (eng.ledger.dir / "audit.ndjson").read_text()
    assert eng.ledger.verify_chain().ok
