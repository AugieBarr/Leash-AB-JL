"""SQLi Hunter tools — confirm and exploit SQL injection on in-scope endpoints.

Both tools are gated by the scope guard. Per the agent's instructions these run
only AFTER the human operator approves in the Band room. ``manual_sqli_probe`` is
the deterministic, fast confirmation used for reliable live demos;
``run_sqlmap`` is the full tool when installed.
"""
from __future__ import annotations

import httpx
from pydantic import BaseModel, Field

from governance.scope_guard import ScopeViolationError, scope_guard
from swarm.control_channel import enforce_gate
from tools._subprocess import ensure_leading_slash, scoped_run, tool_available

_GATE_DENIED = (
    "BLOCKED: human approval required before exploitation. The operator halted "
    "or did not approve this action at the Control Center gate."
)


def sqli_tools(eng, *, gate_timeout: float = 600.0, gate_poll: float = 0.4):
    cap = lambda: eng.cap_for("leash-sqli-hunter")  # noqa: E731 (terse local)

    async def _gate(tool: str, endpoint: str, detail: str) -> bool:
        """Pass iff the operator has approved this endpoint. If not yet approved,
        open the Control Center gate and block on their decision. Enforced here in
        code so the exploit cannot run on the agent's say-so alone."""
        if eng.is_approved(endpoint):
            return True
        return await enforce_gate(
            eng, tool=tool, endpoint=endpoint, detail=detail, timeout=gate_timeout, poll=gate_poll
        )

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
        if not await _gate(
            "manual_sqli_probe", base,
            "single-quote / UNION SQL injection probe on the product search parameter",
        ):
            return _GATE_DENIED
        benign_url = eng.base_url + base + "apple"
        probe_url = eng.base_url + base + "apple'"
        try:
            scope_guard(benign_url, cap())
            scope_guard(probe_url, cap())
        except ScopeViolationError as e:
            await eng.log("error", tool="manual_sqli_probe", path=base, blocked=str(e))
            return f"BLOCKED by scope guard: {e}"

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
        path = ensure_leading_slash(args.path)
        if not await _gate("run_sqlmap", path, "sqlmap injection enumeration"):
            return _GATE_DENIED
        url = eng.base_url + path
        if not tool_available("sqlmap"):
            try:
                scope_guard(url, cap())
            except ScopeViolationError as e:
                return f"BLOCKED by scope guard: {e}"
            await eng.log("tool_result", tool="run_sqlmap", url=url, note="sqlmap not installed; use manual_sqli_probe")
            return "sqlmap is not installed in this environment — use manual_sqli_probe for confirmation."

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
