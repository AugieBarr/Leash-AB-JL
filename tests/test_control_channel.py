"""Tests for the operator control channel — the governed web→engagement bridge.

The channel must (1) never let an unsafe engagement id reach the filesystem,
(2) resolve a gate only on the operator's real decision, failing safe to halt,
(3) keep ``halt`` global while ``approve`` binds to one gate, and (4) leave the
ledger single-writer: the viewer writes a file, the engagement records the event.
"""
import pytest

from swarm.control_channel import (
    await_decision,
    control_dir,
    read_decision,
    request_approval,
    submit_decision,
    watch_halt,
)
from swarm.engagement import open_engagement


def test_safe_id_rejects_traversal(tmp_path):
    for bad in ["../etc", "a/b", "..", "x/../y", ""]:
        with pytest.raises(ValueError):
            control_dir(bad, root=str(tmp_path))
    # A normal id is accepted and lands under the engagement dir.
    assert control_dir("demo-01", root=str(tmp_path)).name == "control"


def test_submit_rejects_unknown_action(tmp_path):
    with pytest.raises(ValueError):
        submit_decision("eng", action="approve_everything", root=str(tmp_path))


def test_submit_and_read_roundtrip(tmp_path):
    rec = submit_decision(
        "eng", action="approve", gate_id="gate-3", operator="josh", root=str(tmp_path)
    )
    assert rec["action"] == "approve" and rec["gate_id"] == "gate-3"
    back = read_decision("eng", root=str(tmp_path))
    assert back == rec


async def test_request_approval_logs_event_and_returns_gate(tmp_path):
    eng = open_engagement("t-ctl-req", "localhost", 3000, root=str(tmp_path))
    gate = await request_approval(eng, tool="manual_sqli_probe", endpoint="/rest/products/search")
    assert gate == "gate-0"  # first event in a fresh chain
    text = (eng.ledger.dir / "audit.ndjson").read_text()
    assert "approval_requested" in text and "manual_sqli_probe" in text


async def test_await_decision_returns_approve_on_matching_gate(tmp_path):
    eng = open_engagement("t-ctl-ok", "localhost", 3000, root=str(tmp_path))
    gate = await request_approval(eng, tool="manual_sqli_probe")
    submit_decision("t-ctl-ok", action="approve", gate_id=gate, root=str(tmp_path))
    assert await await_decision(eng, gate, poll=0.02, timeout=2.0) == "approve"


async def test_approve_for_other_gate_does_not_resolve(tmp_path):
    eng = open_engagement("t-ctl-mismatch", "localhost", 3000, root=str(tmp_path))
    gate = await request_approval(eng, tool="manual_sqli_probe")  # gate-0
    submit_decision("t-ctl-mismatch", action="approve", gate_id="gate-99", root=str(tmp_path))
    # An approval naming a different gate must not satisfy this one → fail safe to halt.
    assert await await_decision(eng, gate, poll=0.02, timeout=0.2) == "halt"


async def test_halt_is_global_across_any_gate(tmp_path):
    eng = open_engagement("t-ctl-halt", "localhost", 3000, root=str(tmp_path))
    gate = await request_approval(eng, tool="run_sqlmap")
    submit_decision("t-ctl-halt", action="halt", gate_id="anything", root=str(tmp_path))
    assert await await_decision(eng, gate, poll=0.02, timeout=2.0) == "halt"


async def test_await_decision_times_out_to_halt(tmp_path):
    eng = open_engagement("t-ctl-timeout", "localhost", 3000, root=str(tmp_path))
    gate = await request_approval(eng, tool="manual_sqli_probe")
    # No decision is ever written — the gate must never default open.
    assert await await_decision(eng, gate, poll=0.02, timeout=0.15) == "halt"


async def test_stale_approval_cleared_on_new_gate(tmp_path):
    eng = open_engagement("t-ctl-stale", "localhost", 3000, root=str(tmp_path))
    g0 = await request_approval(eng, tool="manual_sqli_probe")
    submit_decision("t-ctl-stale", action="approve", gate_id=g0, root=str(tmp_path))
    # Opening a new gate clears the prior decision so it can't carry over.
    g1 = await request_approval(eng, tool="run_sqlmap")
    assert g1 != g0
    assert read_decision("t-ctl-stale", root=str(tmp_path)) is None
    assert await await_decision(eng, g1, poll=0.02, timeout=0.15) == "halt"


async def test_watch_halt_engages_kill_switch(tmp_path):
    eng = open_engagement("t-ctl-watch", "localhost", 3000, root=str(tmp_path))
    submit_decision("t-ctl-watch", action="halt", root=str(tmp_path))
    await watch_halt(eng, poll=0.02)
    assert eng.halted
    assert "kill_switch" in (eng.ledger.dir / "audit.ndjson").read_text()


async def test_chain_stays_valid_through_gate(tmp_path):
    eng = open_engagement("t-ctl-chain", "localhost", 3000, root=str(tmp_path))
    gate = await request_approval(eng, tool="manual_sqli_probe", endpoint="/rest/products/search")
    submit_decision("t-ctl-chain", action="approve", gate_id=gate, root=str(tmp_path))
    await await_decision(eng, gate, poll=0.02, timeout=2.0)
    await eng.log("approval", action="manual_sqli_probe", decision="approved", operator="op", gate_id=gate)
    assert eng.ledger.verify_chain().ok
