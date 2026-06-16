"""XSS Hunter tools — confirm reflected cross-site scripting on in-scope endpoints.

The second offensive specialist (alongside the SQLi Hunter), so the Commander has
a *real* matching decision to make on discovery: a SQL-injection surface recruits
``@leash-sqli-hunter``; a reflected-input surface recruits ``@leash-xss-hunter``.

``manual_xss_probe`` is a sound, generic reflected-XSS confirmation: it injects a
uniquely-marked ``<svg/onload=…>`` payload and confirms XSS **only** when that
payload is reflected *unescaped* in an HTML-context (``text/html``) response. A
payload reflected HTML-escaped, or reflected in a non-HTML body (e.g. JSON), is
reported as *not confirmed* — the tool never claims a finding it cannot stand
behind, matching the recon/misconfig tools' honesty.

Like the SQLi tools, every probe is (1) refused if the kill-switch is engaged,
(2) bounded by the scope guard — an out-of-scope reach is refused by construction
before the gate is ever opened — and (3) blocked behind the code-enforced human
approval gate before any request leaves: exploitation is not on the agent's
say-so alone.
"""
from __future__ import annotations

import httpx
from pydantic import BaseModel, Field

from governance.scope_guard import ScopeViolationError, scope_guard
from swarm.control_channel import enforce_gate
from tools._subprocess import ensure_leading_slash

# A uniquely-marked payload: the token avoids false positives from pre-existing
# page markup, and the <svg/onload=> body is the thing that must survive unescaped
# in an HTML context for the reflection to be exploitable.
_MARKER = "leashXSS9173"
_PAYLOAD = f"{_MARKER}<svg/onload=alert(1)>"

_GATE_DENIED = (
    "BLOCKED: human approval required before exploitation. The operator halted "
    "or did not approve this action at the Control Center gate."
)


def xss_tools(eng, *, gate_timeout: float = 600.0, gate_poll: float = 0.4):
    cap = lambda: eng.cap_for("leash-xss-hunter")  # noqa: E731 (terse local, mirrors sqli_tools)

    async def _gate(tool: str, endpoint: str, detail: str) -> bool:
        """Pass iff the operator has approved this endpoint. If not yet approved,
        open the Control Center gate and block on their decision — enforced in
        code so the injection cannot run on the agent's say-so alone."""
        if eng.is_approved(endpoint):
            return True
        return await enforce_gate(
            eng, tool=tool, endpoint=endpoint, detail=detail, timeout=gate_timeout, poll=gate_poll
        )

    class ManualXssProbeInput(BaseModel):
        """Confirm reflected XSS on an in-scope endpoint by injecting a uniquely-marked <svg/onload> payload and checking whether it is reflected unescaped in an HTML response."""

        path: str = Field(
            default="/rest/products/search?q=",
            description="Endpoint path ending at the reflected parameter, e.g. /rest/products/search?q=",
        )
        param: str = Field(default="q", description="Name of the reflected parameter (for reporting)")

    async def manualxssprobe(args: ManualXssProbeInput) -> str:
        halted = await eng.refuse_if_halted("manual_xss_probe")
        if halted:
            return halted
        base = ensure_leading_slash(args.path)
        # Scope is checked BEFORE the gate (mirrors sqli_tools): an out-of-scope
        # reach fails closed by construction without ever bothering the operator.
        probe_url = eng.base_url + base + _PAYLOAD
        try:
            scope_guard(probe_url, cap())
        except ScopeViolationError as e:
            await eng.log("error", tool="manual_xss_probe", path=base, blocked=str(e))
            return f"BLOCKED by scope guard: {e}"
        if not await _gate(
            "manual_xss_probe", base,
            f"reflected-XSS marker injection on the {args.param} parameter",
        ):
            return _GATE_DENIED

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(probe_url)

        body = resp.text
        content_type = resp.headers.get("content-type", "")
        is_html = "html" in content_type.lower()
        reflected_raw = _PAYLOAD in body
        escaped = _PAYLOAD.replace("<", "&lt;").replace(">", "&gt;")
        reflected_escaped = escaped in body
        confirmed = reflected_raw and is_html

        await eng.log(
            "tool_result",
            tool="manual_xss_probe",
            path=base,
            status=resp.status_code,
            content_type=content_type,
            reflected_unescaped=reflected_raw,
            html_context=is_html,
            confirmed=confirmed,
        )
        if confirmed:
            eng.record_finding(
                type="xss",
                endpoint=base,
                severity="high",
                evidence=f"reflected <svg/onload> payload returned unescaped in {content_type or 'an HTML response'}",
            )
            return (
                f"[VULNERABLE] {base} reflects the {args.param} parameter unescaped into an HTML "
                f"response (content-type {content_type or 'text/html'}) — reflected XSS confirmed; "
                f"the injected <svg/onload> executes."
            )
        if reflected_raw and not is_html:
            return (
                f"[not confirmed] {base}: payload reflected unescaped but content-type is "
                f"{content_type or 'non-HTML'} — not a directly-exploitable reflected XSS."
            )
        if reflected_escaped:
            return f"[not confirmed] {base}: input is reflected but HTML-escaped — not injectable."
        return f"[not confirmed] {base}: marker not reflected in the response — not injectable."

    return [(ManualXssProbeInput, manualxssprobe)]
