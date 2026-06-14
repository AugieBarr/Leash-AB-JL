"""Misconfiguration & exposure tools — a second, deterministic vulnerability class.

Read-only probes (no exploitation) for OWASP A05 (Security Misconfiguration) and
A01 (Broken Access Control / sensitive exposure), each authorized by the scope
guard and recorded to the tamper-evident ledger. Handlers close over the shared
Engagement, exactly like the recon and SQLi tools.

Detection is deterministic and honest:
- ``security_headers_probe`` flags response headers that are *absent* — no
  guessing, just presence/absence on the live response.
- ``exposure_probe`` confirms an exposure only on an actual HTTP 200 from the
  target (e.g. an open ``/ftp`` directory listing, or a version-disclosing
  admin endpoint).

The exposure probe is also where per-specialist scoping shows its teeth: a
capability scoped to ``/rest/products`` makes a ``/ftp`` check fail closed.
"""
from __future__ import annotations

import httpx
from pydantic import BaseModel, Field

from governance.scope_guard import ScopeViolationError, scope_guard

# Security headers a hardened web app should set; absence is the finding.
_EXPECTED_HEADERS = (
    "content-security-policy",
    "strict-transport-security",
    "x-frame-options",
    "x-content-type-options",
    "referrer-policy",
)
# The two whose absence is material enough to record as a finding on its own.
_CRITICAL_HEADERS = ("content-security-policy", "strict-transport-security")

# Paths that, if they answer 200, are exposures rather than features.
_EXPOSURE_CANDIDATES = (
    ("/ftp", "open directory / file store"),
    ("/rest/admin/application-version", "version disclosure"),
)


def misconfig_tools(eng, owner: str = "leash-recon-scout"):
    cap = lambda: eng.cap_for(owner)  # noqa: E731 (terse local, mirrors sqli_tools)

    class SecurityHeadersProbeInput(BaseModel):
        """Check the target for missing HTTP security headers (CSP, HSTS, X-Frame-Options, etc.)."""

        path: str = Field(default="/", description="Path to fetch and inspect headers on, e.g. /")

    async def securityheadersprobe(args: SecurityHeadersProbeInput) -> str:
        halted = await eng.refuse_if_halted("security_headers_probe")
        if halted:
            return halted
        path = args.path if args.path.startswith("/") else "/" + args.path
        url = eng.base_url + path
        try:
            scope_guard(url, cap())
        except ScopeViolationError as e:
            await eng.log("error", tool="security_headers_probe", url=url, blocked=str(e))
            return f"BLOCKED by scope guard: {e}"

        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url)
        present = {h: r.headers.get(h) for h in _EXPECTED_HEADERS if h in r.headers}
        missing = [h for h in _EXPECTED_HEADERS if h not in r.headers]
        critical_missing = [h for h in _CRITICAL_HEADERS if h in missing]

        await eng.log(
            "tool_result",
            tool="security_headers_probe",
            url=url,
            missing=missing,
            present=sorted(present),
        )
        if critical_missing:
            eng.record_finding(
                type="security_misconfiguration",
                endpoint=path,
                severity="medium",
                evidence="missing headers: " + ", ".join(critical_missing),
            )
            return (
                f"[MISCONFIG] {url} is missing security headers: {', '.join(missing)}. "
                f"Critically absent: {', '.join(critical_missing)} (OWASP A05). "
                f"Present: {', '.join(sorted(present)) or 'none'}."
            )
        return f"[ok] {url} sets the critical security headers; missing only: {', '.join(missing) or 'none'}."

    class ExposureProbeInput(BaseModel):
        """Probe well-known sensitive paths (open directories, admin/version endpoints) that should not be public."""

    async def exposureprobe(args: ExposureProbeInput) -> str:
        exposures = []
        async with httpx.AsyncClient(timeout=10.0) as client:
            for path, label in _EXPOSURE_CANDIDATES:
                url = eng.base_url + path
                try:
                    scope_guard(url, cap())
                except ScopeViolationError as e:
                    exposures.append({"path": path, "blocked": str(e)[:80]})
                    continue
                try:
                    r = await client.get(url)
                except Exception as e:  # one bad path shouldn't abort the sweep
                    exposures.append({"path": path, "error": str(e)[:80]})
                    continue
                if r.status_code == 200:
                    exposures.append({"path": path, "status": 200, "label": label})
                    eng.record_finding(
                        type="sensitive_exposure",
                        endpoint=path,
                        severity="medium",
                        evidence=f"{label} reachable (HTTP 200)",
                    )
                else:
                    exposures.append({"path": path, "status": r.status_code})

        await eng.log("tool_result", tool="exposure_probe", exposures=exposures)
        confirmed = [e for e in exposures if e.get("status") == 200]
        blocked = [e for e in exposures if e.get("blocked")]
        head = (
            f"[EXPOSED] {len(confirmed)} sensitive path(s) reachable: "
            + ", ".join(f"{e['path']} ({e['label']})" for e in confirmed)
            if confirmed
            else "[none reachable in scope]"
        )
        if blocked:
            head += "  |  scope-guarded (out of capability): " + ", ".join(e["path"] for e in blocked)
        return head

    return [
        (SecurityHeadersProbeInput, securityheadersprobe),
        (ExposureProbeInput, exposureprobe),
    ]
