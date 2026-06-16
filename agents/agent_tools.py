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

# The non-brain Leash specialists the Commander may recruit on discovery. A guard,
# not a convention: the target's HTTP responses reach the Commander's context, so a
# prompt-injected Commander must not be able to pull an arbitrary agent_label into
# the room. Brain agents (commander/scope-warden/auditor) are seeded at room
# creation, never recruited; mirror swarm.seed.SWARM minus the brain tier.
_RECRUITABLE = frozenset(
    {
        "leash-recon-scout",
        "leash-sqli-hunter",
        "leash-xss-hunter",
        "leash-auth-breaker",
        "leash-injection-tester",
        "leash-data-sentinel",
        "leash-reporter",
    }
)


def commander_tools(eng):
    class IssueKillSwitchInput(BaseModel):
        """Engage the engagement kill-switch: immediately stop all offensive tools and record the halt. Use the moment the operator says "halt", or on any out-of-scope or destructive risk."""

        reason: str = Field(
            default="operator kill-switch",
            description="Why the engagement is being halted (recorded to the audit chain)",
        )

    async def issuekillswitch(args: IssueKillSwitchInput) -> str:
        seq = await eng.halt(args.reason)
        msg = (
            f"KILL-SWITCH ENGAGED (audit seq={seq}): {args.reason}. Every offensive tool is "
            f"now refused in-process and the refusal is logged."
        )
        if not eng.band_room_id:
            return msg + " (No Band room bound — in-process halt only.)"
        # Eject the swarm Band-side in code, not by asking the LLM to call a platform tool —
        # so the room visibly disbands as a deterministic consequence of the kill-switch.
        # Lazy import so governance-only contexts (and tests) need no Band SDK.
        from swarm.kill_switch import eject_room

        try:
            removed = await eject_room(eng.band_room_id)
        except Exception as e:
            await eng.log("error", tool="issue_kill_switch", room=eng.band_room_id, error=str(e))
            return (
                msg + f" Band-side eject FAILED ({e}); remove specialists manually: "
                f"python -m swarm.kill_switch --room {eng.band_room_id}."
            )
        await eng.log("ejected", room=eng.band_room_id, removed=removed)
        return msg + f" Ejected {len(removed)} specialist(s) from the room: {', '.join(removed) or '(none)'}."

    class RecruitSpecialistInput(BaseModel):
        """Bring a specialist agent into the Band room on discovery — e.g. recruit the SQLi Hunter once recon surfaces an injectable endpoint. The specialist starts receiving room @mentions immediately, and the recruitment is recorded to the audit chain."""

        agent_label: str = Field(
            description="Specialist to recruit, e.g. leash-recon-scout, leash-sqli-hunter, leash-reporter"
        )

    async def recruitspecialist(args: RecruitSpecialistInput) -> str:
        if args.agent_label not in _RECRUITABLE:
            # Refused in code before any lookup or Band call — even a prompt-injected
            # Commander can only ever recruit the known, governed specialist roster.
            await eng.log("error", tool="recruit_specialist", agent=args.agent_label, error="not a recruitable specialist")
            return (
                f"RECRUIT REFUSED: {args.agent_label!r} is not a recruitable Leash specialist "
                f"(allowed: {', '.join(sorted(_RECRUITABLE))})."
            )
        if not eng.band_room_id:
            return "Cannot recruit: this engagement is not bound to a Band room (launch with --seed)."
        # Lazy import so governance-only contexts (and tests) need no Band SDK.
        from band.client.rest import DEFAULT_REQUEST_OPTIONS, ParticipantRequest
        from band.config import load_agent_config

        from swarm._band_client import band_client

        try:
            spec_id = load_agent_config(args.agent_label)[0]
            commander_key = load_agent_config("leash-commander")[1]
            client = band_client(commander_key)
            await client.agent_api_participants.add_agent_chat_participant(
                chat_id=eng.band_room_id,
                participant=ParticipantRequest(participant_id=spec_id, role="member"),
                request_options=DEFAULT_REQUEST_OPTIONS,
            )
        except Exception as e:
            await eng.log("error", tool="recruit_specialist", agent=args.agent_label, error=str(e))
            return f"RECRUIT FAILED for {args.agent_label}: {e}"
        await eng.log("recruited", agent=args.agent_label, room=eng.band_room_id)
        return f"Recruited {args.agent_label} into the room — they now receive @mentions and can act."

    return [(IssueKillSwitchInput, issuekillswitch), (RecruitSpecialistInput, recruitspecialist)]


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
        tail = eng.ledger.tail_hash_hex
        # Broadcast the seal into the Band room as a code-dispatched event (not an LLM
        # @mention): the room transcript becomes the governance record. Best-effort —
        # the offline bundle is the source of truth, so a Band hiccup never fails the seal.
        broadcast = ""
        if eng.band_room_id:
            from swarm._band_client import post_governance_signal

            signal = (
                f"AUDIT SEALED — {path.name} | chain tail {tail[:16]}… | "
                f"{len(eng.findings)} findings | verify offline: "
                f"python -m governance.verify {path.name}"
            )
            try:
                await post_governance_signal(eng, signal)
                await eng.log("seal_broadcast", room=eng.band_room_id, tail=tail)
                broadcast = " Seal posted to the Band room."
            except Exception as e:
                await eng.log("error", tool="seal_broadcast", room=eng.band_room_id, error=str(e))
                broadcast = f" (Band broadcast failed: {e})"
        return (
            f"Sealed bundle: {path.name} | chain tail {tail[:16]}… | "
            f"{len(eng.findings)} findings. Verify offline with: "
            f"python -m governance.verify {path.name}" + broadcast
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

    _SEV_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}

    async def renderreport(args: RenderReportInput) -> str:
        findings = sorted(
            eng.findings, key=lambda f: _SEV_ORDER.get(str(f.get("severity", "info")).lower(), 5)
        )
        counts: dict[str, int] = {}
        for f in findings:
            sev = str(f.get("severity", "info")).lower()
            counts[sev] = counts.get(sev, 0) + 1
        rollup = ", ".join(f"{counts[s]} {s}" for s in sorted(counts, key=lambda s: _SEV_ORDER.get(s, 5))) or "none"
        pubkey_b64 = base64.b64encode(eng.ledger.public_key_bytes()).decode("ascii")
        generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")

        lines = [
            f"# Leash Pentest Report — {eng.engagement_id}",
            "",
            f"- **Target:** {eng.target_host}:{eng.target_port} (authorized lab target)",
            f"- **Generated:** {generated}",
            f"- **Engagement status:** {'HALTED by kill-switch' if eng.halted else 'completed'}",
            "",
            "## Executive summary",
            "",
            f"{len(findings)} finding(s) recorded — {rollup}. Every action below is bound into a "
            "tamper-evident, Ed25519-signed audit chain; the attestation at the foot of this report "
            "lets any third party verify it offline without trusting this run.",
            "",
            "## Findings",
            "",
        ]
        if not findings:
            lines.append("_No findings recorded._")
        else:
            lines.append("| # | Severity | Type | Endpoint | Evidence |")
            lines.append("|---|---|---|---|---|")
            for i, f in enumerate(findings, 1):
                lines.append(
                    f"| {i} | {f.get('severity', 'info')} | {f.get('type', 'finding')} "
                    f"| `{f.get('endpoint', '')}` | {f.get('evidence', '')} |"
                )

        lines += [
            "",
            "## Audit attestation",
            "",
            f"- **Events in chain:** {eng.ledger.head.seq}",
            f"- **Chain tail (SHA-256):** `{eng.ledger.tail_hash_hex}`",
            f"- **Ed25519 public key (base64):** `{pubkey_b64}`",
            "- **Verify offline:** `python -m governance.verify <engagement>_bundle.tar.gz`",
            "",
            "_The public key above is the one sealed into the bundle; a passing verification proves "
            "no event was added, removed, or altered after the fact._",
        ]
        report = "\n".join(lines)
        report_path = eng.ledger.dir / "report.md"
        report_path.write_text(report + "\n")
        await eng.log("report_rendered", findings=len(findings), path=str(report_path.name))
        return report

    return [(RenderReportInput, renderreport)]
