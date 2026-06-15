"""The exploitation tools enforce the human approval gate in CODE, not by prompt.

These tests prove two governance invariants without touching the network:
1. An out-of-scope target is refused by the scope guard *before* any gate opens.
2. The gate is fail-closed — a HALT decision stops the tool before it probes, and
   the engagement is halted.

The approve path is exercised by the offline/control demos (it needs a live
target), so it is not unit-tested here.
"""
import asyncio
import json

from governance.capability import ScopeSpec, issue_capability
from swarm.control_channel import submit_decision
from swarm.engagement import open_engagement
from tools.sqli_tools import sqli_tools


def _manual_probe(eng):
    for model, handler in sqli_tools(eng):
        if model.__name__ == "ManualSqliProbeInput":
            return model, handler
    raise AssertionError("ManualSqliProbeInput tool not found")


def _scope_to_products(eng):
    eng.capabilities["leash-sqli-hunter"] = issue_capability(
        eng.root_cap,
        ScopeSpec.of(["localhost"], [3000], ["/rest/products"]),
        agent_id="leash-sqli-hunter",
    )


def _kinds(tmp_path, engagement_id):
    ndjson = tmp_path / engagement_id / "audit.ndjson"
    return [json.loads(line)["kind"] for line in ndjson.read_text().splitlines() if line.strip()]


async def test_out_of_scope_refused_before_the_gate(tmp_path):
    """An out-of-scope path is blocked by the scope guard; the gate never opens."""
    eng = open_engagement("gate-scope", "localhost", 3000, root=str(tmp_path))
    _scope_to_products(eng)
    model, probe = _manual_probe(eng)

    out = await probe(model(path="/ftp"))

    assert "BLOCKED by scope guard" in out
    assert "approval_requested" not in _kinds(tmp_path, "gate-scope")
    assert not eng.halted


async def test_in_scope_blocks_at_human_gate_on_halt(tmp_path):
    """An in-scope probe opens the gate and fails closed when the operator HALTs —
    without ever issuing an HTTP request."""
    eng = open_engagement("gate-halt", "localhost", 3000, root=str(tmp_path))
    _scope_to_products(eng)
    model, probe = _manual_probe(eng)
    ndjson = tmp_path / "gate-halt" / "audit.ndjson"

    async def halt_once_the_gate_opens():
        for _ in range(200):
            if ndjson.exists() and "approval_requested" in ndjson.read_text():
                break
            await asyncio.sleep(0.02)
        submit_decision("gate-halt", action="halt", root=str(tmp_path))

    halter = asyncio.create_task(halt_once_the_gate_opens())
    out = await probe(model(path="/rest/products/search?q="))
    await halter

    assert "BLOCKED at the human gate" in out
    assert eng.halted
    kinds = _kinds(tmp_path, "gate-halt")
    assert "approval_requested" in kinds  # the gate was opened
    assert "tool_result" not in kinds  # but the probe never ran
