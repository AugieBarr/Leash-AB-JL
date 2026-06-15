"""Operator control channel — the governed bridge between the web Control Center
and a running engagement.

The viewer is a SEPARATE process from the swarm, and the audit ledger is
single-writer: one ``asyncio.Lock`` guards the chain *within* a process, but two
processes appending to the same ``audit.ndjson`` would race and corrupt it. So
the Control Center never writes to the ledger itself. It drops a small *decision
file*; the engagement — the sole ledger writer — polls it and records the
governed ``approval`` / ``kill_switch`` event.

Net effect: an operator clicks APPROVE or HALT in the browser, and that decision
lands in the tamper-evident chain, signed and in order by the one writer —
exactly as a room-typed approval would, with none of the multi-writer risk.

On-disk, under ``engagements/<id>/control/``:
    decision.json   — written by the viewer (operator action), read by the engagement

Flow:
    1. A specialist needs approval → ``request_approval`` logs ``approval_requested``.
       The viewer sees it over SSE and shows APPROVE / HALT.
    2. Operator clicks → viewer ``POST /control`` → ``submit_decision`` writes decision.json.
    3. The specialist's ``await_decision`` sees the matching gate and returns the
       action; the caller records ``approval`` (approve) or calls ``eng.halt`` (halt).
    4. ``watch_halt`` lets the kill-switch stop even a long-running live swarm: it
       polls decision.json and halts the engagement the instant a halt lands.

This module has no Band-SDK imports, so the whole mechanism is unit-testable
offline — like everything under ``governance/``.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
from pathlib import Path
from typing import Optional

# Engagement ids name a directory, so they must never carry a path separator or a
# parent reference. This allowlist is the structural defense against traversal
# (e.g. an id of ``../../etc``) — callers reaching the filesystem go through it.
_SAFE_ID = re.compile(r"[A-Za-z0-9_-]+")

_ACTIONS = ("approve", "halt")


def _safe_id(engagement_id: str) -> str:
    if not _SAFE_ID.fullmatch(engagement_id or ""):
        raise ValueError(f"unsafe engagement id: {engagement_id!r}")
    return engagement_id


def control_dir(engagement_id: str, root: str | os.PathLike = "engagements") -> Path:
    return Path(root) / _safe_id(engagement_id) / "control"


def decision_path(engagement_id: str, root: str | os.PathLike = "engagements") -> Path:
    return control_dir(engagement_id, root) / "decision.json"


# ----- engagement side (the sole ledger writer) -------------------------------
async def request_approval(eng, *, tool: str, endpoint: str = "", detail: str = "") -> str:
    """Open a human-approval gate. Logs an ``approval_requested`` event the viewer
    renders as an APPROVE / HALT prompt, and returns a deterministic ``gate_id``
    tied to the event's own sequence number (no randomness — the chain seq is the
    natural unique id, and it keeps replays reproducible).

    A stale decision file from an earlier gate is cleared first, so a previous
    "approve" can never silently satisfy a fresh gate.
    """
    gate_id = f"gate-{eng.ledger.head.seq}"
    path = decision_path(eng.engagement_id, eng.ledger.dir.parent)
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    await eng.log("approval_requested", gate_id=gate_id, tool=tool, endpoint=endpoint, detail=detail)
    return gate_id


async def await_decision(
    eng, gate_id: str, *, poll: float = 0.4, timeout: float = 300.0
) -> str:
    """Block until the operator decides this gate, returning ``"approve"`` or
    ``"halt"``. Fails safe: a timeout, or an in-process halt landing by any other
    path, both resolve to ``"halt"`` — the gate never defaults open.

    A ``halt`` decision is global (it stops the whole engagement), so it resolves
    any gate regardless of ``gate_id``; an ``approve`` only resolves the gate it
    names, so an approval meant for an earlier gate cannot carry over.
    """
    path = decision_path(eng.engagement_id, eng.ledger.dir.parent)
    deadline = time.monotonic() + timeout
    while True:
        if eng.halted:
            return "halt"
        rec = _read(path)
        if rec is not None:
            action = rec.get("action")
            if action == "halt":
                return "halt"
            if action == "approve" and rec.get("gate_id") == gate_id:
                return "approve"
        if time.monotonic() >= deadline:
            return "halt"
        await asyncio.sleep(poll)


async def watch_halt(eng, *, poll: float = 0.5) -> str:
    """Run alongside a live swarm: poll the decision file and engage the
    kill-switch the moment a ``halt`` lands, so the Control Center's KILL button
    stops even agents that are mid-task. Returns once the engagement is halted."""
    path = decision_path(eng.engagement_id, eng.ledger.dir.parent)
    while not eng.halted:
        rec = _read(path)
        if rec is not None and rec.get("action") == "halt":
            await eng.halt("operator kill-switch (control center)")
            return "halt"
        await asyncio.sleep(poll)
    return "halt"


# ----- viewer side (operator action; never touches the ledger) ----------------
def submit_decision(
    engagement_id: str,
    *,
    action: str,
    gate_id: str = "",
    operator: str = "operator",
    root: str | os.PathLike = "engagements",
    now_ms: Optional[int] = None,
) -> dict:
    """Record the operator's decision as a file the engagement will pick up. This
    is the only write the viewer performs, and it deliberately does NOT touch the
    ledger — the engagement records the signed governed event. Validates the
    action and the engagement id (allowlist) before writing; the write is atomic
    so the poller never reads a half-written file."""
    if action not in _ACTIONS:
        raise ValueError(f"unknown action {action!r}; expected one of {_ACTIONS}")
    cdir = control_dir(engagement_id, root)
    cdir.mkdir(parents=True, exist_ok=True)
    record = {
        "action": action,
        "gate_id": gate_id,
        "operator": operator,
        "ts_ms": now_ms if now_ms is not None else int(time.time() * 1000),
    }
    path = cdir / "decision.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(record), encoding="utf-8")
    os.replace(tmp, path)  # atomic on POSIX — poller sees all-or-nothing
    return record


def read_decision(engagement_id: str, root: str | os.PathLike = "engagements") -> Optional[dict]:
    return _read(decision_path(engagement_id, root))


def clear_decision(engagement_id: str, root: str | os.PathLike = "engagements") -> None:
    try:
        decision_path(engagement_id, root).unlink()
    except FileNotFoundError:
        pass


def _read(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None
