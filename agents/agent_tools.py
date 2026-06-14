"""Custom tools for the governance agents (Commander, ScopeWarden, Auditor, Reporter).

These act on the shared Engagement: engaging the kill-switch, issuing restricted
capabilities, sealing and verifying the audit chain, and rendering the final
report. Like all custom tools, handlers receive only their validated input and
return a string; Band coordination happens via the platform tools the LLM calls
separately.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from governance.bundle import export_bundle
from governance.capability import ScopeSpec, issue_capability
from governance.scope_guard import parse_target


def commander_tools(eng):
    class IssueKillSwitchInput(BaseModel):
        """Engage the engagement kill-switch: immediately stop all offensive tools and record the halt. Use the moment the operator says "halt", or on any out-of-scope or destructive risk."""

        reason: str = Field(
            default="operator kill-switch",
            description="Why the engagement is being halted (recorded to the audit chain)",
        )

    async def issuekillswitch(args: IssueKillSwitchInput) -> str:
        seq = await eng.halt(args.reason)
        return (
            f"KILL-SWITCH ENGAGED (audit seq={seq}): {args.reason}. Every offensive tool is "
            f"now refused in-process and the refusal is logged. Complete the eject by removing "
            f"each specialist from the room (thenvoi_remove_participant)."
        )

    return [(IssueKillSwitchInput, issuekillswitch)]


def scope_warden_tools(eng):
    class IssueCapabilityInput(BaseModel):
        """Issue a restricted child capability to a specialist agent, narrowed to the given path prefixes within the engagement target."""

        agent_label: str = Field(description="Agent to scope, e.g. leash-sqli-hunter")
        paths: list[str] = Field(
            default_factory=lambda: ["/"],
            description="Path prefixes the agent may touch, e.g. ['/rest/products']",
        )

    async def issuecapability(args: IssueCapabilityInput) -> str:
        restriction = ScopeSpec.of([eng.target_host], [eng.target_port], args.paths)
        try:
            child = issue_capability(eng.root_cap, restriction, agent_id=args.agent_label)
        except Exception as e:
            await eng.log("error", tool="issue_capability", agent=args.agent_label, error=str(e))
            return f"DENIED: cannot issue {args.agent_label} a capability for {args.paths}: {e}"
        eng.capabilities[args.agent_label] = child
        await eng.log(
            "capability_issued",
            agent=args.agent_label,
            cap_id=child.id,
            hosts=list(child.scope.hosts),
            ports=list(child.scope.ports),
            paths=list(child.scope.paths),
        )
        return (
            f"Issued {args.agent_label} capability {child.id[:8]} scoped to "
            f"{eng.target_host}:{eng.target_port} paths={list(child.scope.paths)}."
        )

    class CheckCapabilityInput(BaseModel):
        """Check whether an agent's capability permits a target URL."""

        agent_label: str = Field(description="Agent whose capability to check")
        url: str = Field(description="Target URL or host:port/path")

    async def checkcapability(args: CheckCapabilityInput) -> str:
        from governance.capability import check_capability

        cap = eng.cap_for(args.agent_label)
        target = parse_target(args.url)
        allowed = check_capability(cap, target)
        await eng.log("capability_check", agent=args.agent_label, url=args.url, allowed=allowed)
        verdict = "PERMITTED" if allowed else "DENIED"
        return f"{verdict}: {args.agent_label} -> {target.host}:{target.port}{target.path}"

    return [(IssueCapabilityInput, issuecapability), (CheckCapabilityInput, checkcapability)]


def auditor_tools(eng):
    class AppendEventInput(BaseModel):
        """Record a narrative audit event (e.g. a decision or milestone) to the tamper-evident chain."""

        kind: str = Field(description="Event kind, e.g. decision, milestone, note")
        summary: str = Field(description="Short human-readable summary")

    async def appendevent(args: AppendEventInput) -> str:
        seq = await eng.log(args.kind, note=args.summary)
        return f"Recorded event seq={seq} kind={args.kind}."

    class SealBundleInput(BaseModel):
        """Verify the audit chain and seal it into a portable, independently-verifiable bundle."""

    async def sealbundle(args: SealBundleInput) -> str:
        try:
            path = export_bundle(
                eng.engagement_id,
                root=str(eng.ledger.dir.parent),
                target=f"{eng.target_host}:{eng.target_port}",
                findings=eng.findings,
            )
        except Exception as e:
            return f"SEAL FAILED: {e}"
        return (
            f"Sealed bundle: {path.name} | chain tail {eng.ledger.tail_hash_hex[:16]}… | "
            f"{len(eng.findings)} findings. Verify offline with: "
            f"python -m governance.verify {path.name}"
        )

    class VerifyChainInput(BaseModel):
        """Re-verify the audit chain end to end and report whether any tampering is detected."""

    async def verifychain(args: VerifyChainInput) -> str:
        result = eng.ledger.verify_chain()
        return result.detail

    return [
        (AppendEventInput, appendevent),
        (SealBundleInput, sealbundle),
        (VerifyChainInput, verifychain),
    ]


def reporter_tools(eng):
    class RenderReportInput(BaseModel):
        """Render the final pentest report from the recorded findings and the sealed audit chain."""

    async def renderreport(args: RenderReportInput) -> str:
        lines = [
            f"# Leash Pentest Report — {eng.engagement_id}",
            f"Target: {eng.target_host}:{eng.target_port}",
            f"Audit chain tail: {eng.ledger.tail_hash_hex}",
            "",
            "## Findings",
        ]
        if not eng.findings:
            lines.append("- (none recorded)")
        for i, f in enumerate(eng.findings, 1):
            lines.append(f"{i}. **{f.get('type', 'finding')}** — {f.get('endpoint', '')} "
                         f"[{f.get('severity', 'info')}] {f.get('evidence', '')}".rstrip())
        report = "\n".join(lines)
        report_path = eng.ledger.dir / "report.md"
        report_path.write_text(report + "\n")
        await eng.log("report_rendered", findings=len(eng.findings), path=str(report_path.name))
        return report

    return [(RenderReportInput, renderreport)]
