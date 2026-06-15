"""SQLi Hunter tools — confirm and exploit SQL injection on in-scope endpoints.

Every exploitation tool passes through two hard, code-enforced gates before it
touches the target: the scope guard (fail-closed allowlist) and the human
approval gate. The approval gate is enforced *here, in the tool* — not left to
the agent's prompt — so it fires identically in the deterministic demo and in
the live LLM-driven swarm. ``manual_sqli_probe`` is the fast, reliable
confirmation; ``run_sqlmap`` is the full tool when installed.
"""
from __future__ import annotations

import httpx
from pydantic import BaseModel, Field

from governance.scope_guard import ScopeViolationError, scope_guard
from swarm.control_channel import await_decision, request_approval
from tools._subprocess import ensure_leading_slash, scoped_run, tool_available


def sqli_tools(eng):
    cap = lambda: eng.cap_for("leash-sqli-hunter")  # noqa: E731 (terse local)

    async def _human_gate(tool_name: str, endpoint: str, detail: str) -> str | None:
        """Code-enforced human approval gate, fired before any exploitation runs.

        Returns ``None`` when cleared to proceed, or a refusal string otherwise.
        An engagement that pre-authorizes the action (``eng.approvals`` — used by
        the deterministic offline demo) skips the wait; everyone else blocks on the
        operator's APPROVE / HALT in the Control Center, and the granted approval is
        recorded into the tamper-evident chain. Because this lives in the tool, the
        gate is a property of the code path, not of LLM compliance."""
        if tool_name in eng.approvals:
            return None
        gate = await request_approval(eng, tool=tool_name, endpoint=endpoint, detail=detail)
        decision = await await_decision(eng, gate)
        if decision != "approve":
            if not eng.halted:
                await eng.halt(f"operator declined exploitation at the human gate ({tool_name})")
            return f"BLOCKED at the human gate: {tool_name} was not approved by the operator."
        await eng.log("approval", action=tool_name, decision="approved", operator="operator", gate_id=gate)
        eng.approvals.add(tool_name)
        return None

    class ManualSqliProbeInput(BaseModel):
        """Deterministically confirm SQL injection on an in-scope endpoint by comparing a benign value to a single-quote probe."""

        path: str = Field(
            default="/rest/products/search?q=",
            description="Endpoint path ending at the injectable parameter, e.g. /rest/products/search?q=",
        )

    async def manualsqliprobe(args: ManualSqliProbeInput) -> str:
        halted = await eng.refuse_if_halted("manual_sqli_probe")
        if halted:
            return halted
        base = ensure_leading_slash(args.path)
        benign_url = eng.base_url + base + "apple"
        probe_url = eng.base_url + base + "apple'"
        try:
            scope_guard(benign_url, cap())
            scope_guard(probe_url, cap())
        except ScopeViolationError as e:
            await eng.log("error", tool="manual_sqli_probe", path=base, blocked=str(e))
            return f"BLOCKED by scope guard: {e}"

        gated = await _human_gate(
            "manual_sqli_probe", base, "single-quote / UNION SQL-injection probe on the search parameter"
        )
        if gated:
            return gated

        async with httpx.AsyncClient(timeout=10.0) as client:
            benign = await client.get(benign_url)
            probe = await client.get(probe_url)

        injectable = probe.status_code >= 500 or "SQL" in probe.text.upper()
        await eng.log(
            "tool_result",
            tool="manual_sqli_probe",
            path=base,
            baseline_status=benign.status_code,
            probe_status=probe.status_code,
            injectable=injectable,
        )
        if injectable:
            eng.record_finding(
                type="sqli",
                endpoint=base,
                severity="high",
                evidence=f"single-quote injection -> HTTP {probe.status_code}",
            )
            return (
                f"[VULNERABLE] {base} is SQL-injectable. Baseline q=apple -> {benign.status_code}; "
                f"q=apple' -> {probe.status_code} with a SQL error surfaced. UNION-based extraction is feasible."
            )
        return f"[not confirmed] {base}: baseline {benign.status_code}, probe {probe.status_code}."

    class RunSqlmapInput(BaseModel):
        """Run sqlmap against an in-scope endpoint parameter to enumerate the injection (uses --batch, low level for speed)."""

        path: str = Field(description="Endpoint path including the parameter, e.g. /rest/products/search?q=apple")
        param: str = Field(default="q", description="Injectable parameter name")

    async def runsqlmap(args: RunSqlmapInput) -> str:
        halted = await eng.refuse_if_halted("run_sqlmap")
        if halted:
            return halted
        url = eng.base_url + ensure_leading_slash(args.path)
        if not tool_available("sqlmap"):
            try:
                scope_guard(url, cap())
            except ScopeViolationError as e:
                return f"BLOCKED by scope guard: {e}"
            await eng.log("tool_result", tool="run_sqlmap", url=url, note="sqlmap not installed; use manual_sqli_probe")
            return "sqlmap is not installed in this environment — use manual_sqli_probe for confirmation."

        gated = await _human_gate("run_sqlmap", url, f"sqlmap enumeration on parameter {args.param}")
        if gated:
            return gated

        cmd = ["sqlmap", "-u", url, "-p", args.param, "--batch", "--level=1", "--risk=1", "--technique=U", "--flush-session"]
        result = await scoped_run(cmd, url, cap(), timeout=120.0, halted=eng.halted)
        injectable = "is vulnerable" in result["stdout"] or "injectable" in result["stdout"].lower()
        await eng.log(
            "tool_result",
            tool="run_sqlmap",
            url=url,
            returncode=result["returncode"],
            injectable=injectable,
        )
        if injectable:
            eng.record_finding(type="sqli", endpoint=args.path, severity="high", evidence="sqlmap confirmed")
        tail = result["stdout"][-800:]
        return f"sqlmap rc={result['returncode']} injectable={injectable}\n{tail}"

    return [
        (ManualSqliProbeInput, manualsqliprobe),
        (RunSqlmapInput, runsqlmap),
    ]
