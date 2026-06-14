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
