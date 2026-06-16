"""Engagement — the shared, in-process governance state for one pentest run.

The whole swarm runs in a single event loop, so every agent's tool handlers
close over one ``Engagement``: one tamper-evident ledger, one capability
registry, one findings list. Agents still coordinate *through Band* (rooms,
@mentions, recruiting); the Engagement is the governance substrate beneath that.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional

from governance.audit_ledger import AuditLedger
from governance.capability import Capability, ScopeSpec, root_capability
from governance.scope_guard import parse_target


@dataclass
class Engagement:
    engagement_id: str
    target_host: str
    target_port: int
    ledger: AuditLedger
    root_cap: Capability
    capabilities: dict[str, Capability] = field(default_factory=dict)
    findings: list[dict] = field(default_factory=list)
    approvals: set[str] = field(default_factory=set)
    halted: bool = False
    # Band room this engagement coordinates in (set by the launcher when it seeds).
    # Lets the Commander's recruit tool add specialists to the right room.
    band_room_id: str = ""

    @property
    def base_url(self) -> str:
        return f"http://{self.target_host}:{self.target_port}"

    def cap_for(self, agent_label: str) -> Capability:
        """The agent's issued capability, or the engagement root cap as fallback."""
        return self.capabilities.get(agent_label, self.root_cap)

    async def log(self, kind: str, **payload) -> int:
        """Append a structured event to the tamper-evident ledger. Returns seq."""
        return await self.ledger.append(kind, json.dumps(payload, sort_keys=True))

    def record_finding(self, **finding) -> None:
        self.findings.append(finding)

    async def halt(self, reason: str = "operator kill-switch") -> int:
        """Engage the kill-switch: record it and stop all further offensive tools.

        The flag is enforced *in-process* by every target-touching tool (see
        ``refuse_if_halted``), so a halt cannot be ignored by a misbehaving
        agent — it is not a polite request. Idempotent: a second halt re-logs.
        """
        self.halted = True
        return await self.log("kill_switch", reason=reason, halted=True)

    async def refuse_if_halted(self, tool: str) -> Optional[str]:
        """If halted, audit the refused attempt and return the refusal message;
        otherwise return ``None`` so the caller proceeds. Offensive tools call
        this first, making the kill-switch a hard, recorded gate."""
        if not self.halted:
            return None
        await self.log("blocked_halted", tool=tool)
        return "HALTED: engagement stopped by kill-switch — no further actions permitted."

    # ----- human approval gate -------------------------------------------
    def approval_key(self, path: str) -> str:
        """Normalize an endpoint path to the canonical key approvals are recorded
        under, so ``record_approval`` and ``is_approved`` always agree regardless
        of query string, ``*`` markers, or ``..`` (reuses the scope guard's own
        parser). e.g. ``/rest/products/search?q=`` -> ``/rest/products/search``."""
        p = path if path.startswith("/") else "/" + path
        return parse_target(self.base_url + p).path

    async def record_approval(
        self, path: str, *, gate_id: str = "", operator: str = "operator", tool: str = ""
    ) -> int:
        """Record a human approval for ``path`` — both in queryable state (so a
        tool can refuse without it) and as a signed ``approval`` event in the
        tamper-evident chain (so *who approved what* is bound into the audit
        trail). Returns the event seq."""
        key = self.approval_key(path)
        self.approvals.add(key)
        return await self.log(
            "approval", endpoint=key, gate_id=gate_id, operator=operator, tool=tool, decision="approved"
        )

    def is_approved(self, path: str) -> bool:
        """Has the operator approved exploitation of this endpoint? The offensive
        tools check this in code — the gate is not merely something the agent is
        prompted to honour.

        Granularity is **per-endpoint and persists for the engagement** — a
        deliberate product choice: the operator authorizes *exploiting this
        endpoint*, after which a specialist may probe it (e.g. a manual probe
        then sqlmap on the same path) without re-prompting on every payload. The
        scope is the normalized path (query string dropped), so the approval can't
        be widened by query/`*`/`..` decoration. If finer control is ever needed,
        key ``approvals`` by ``(tool, endpoint)`` or add a time-box here; nothing
        else has to change because every offensive tool funnels through this check.
        """
        return self.approval_key(path) in self.approvals


def open_engagement(
    engagement_id: str,
    host: str = "localhost",
    port: int = 3000,
    *,
    root: str = "engagements",
    paths: Optional[list[str]] = None,
) -> Engagement:
    ledger = AuditLedger(engagement_id, root=root)
    scope = ScopeSpec.of([host], [int(port)], tuple(paths) if paths else ("/",))
    cap = root_capability("leash-scope-warden", scope)
    return Engagement(engagement_id, host, int(port), ledger, cap)
