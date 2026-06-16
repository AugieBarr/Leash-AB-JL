"""Recon Scout tools — map the target's attack surface over HTTP.

Read-only probes (no exploitation), each authorized by the scope guard and
recorded to the tamper-evident ledger. The handlers close over the shared
Engagement.
"""
from __future__ import annotations

import httpx
from pydantic import BaseModel, Field

from governance.scope_guard import ScopeViolationError, scope_guard
from tools._subprocess import ensure_leading_slash

# Endpoints worth checking on a Juice-Shop-style target. Probing is real HTTP;
# the SQLi hint below is analyst domain knowledge, surfaced for the LLM to act on.
_RECON_CANDIDATES = [
    "/",
    "/rest/products/search?q=apple",
    "/api/Products",
    "/rest/admin/application-version",
    "/api/Users",
    "/rest/user/login",
]


def recon_tools(eng):
    cap = lambda: eng.cap_for("leash-recon-scout")  # noqa: E731 (terse local, mirrors sqli/misconfig)

    class HttpProbeInput(BaseModel):
        """GET an in-scope path on the target and report status, server header, and notable hints."""

        path: str = Field(
            default="/",
            description="Path on the target, e.g. /rest/products/search?q=apple",
        )

    async def httpprobe(args: HttpProbeInput) -> str:
        halted = await eng.refuse_if_halted("http_probe")
        if halted:
            return halted
        path = ensure_leading_slash(args.path)
        url = eng.base_url + path
        try:
            scope_guard(url, cap())
        except ScopeViolationError as e:
            await eng.log("error", tool="http_probe", url=url, blocked=str(e))
            return f"BLOCKED by scope guard: {e}"

        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url)
        body = r.text[:600]
        hint = "possible-sql" if "SQL" in body.upper() else "none"
        await eng.log("tool_result", tool="http_probe", url=url, status=r.status_code, hint=hint)
        return (
            f"GET {url} -> {r.status_code}; server={r.headers.get('server', '?')}; "
            f"hint={hint}; body[:200]={body[:200]!r}"
        )

    class CrawlTargetInput(BaseModel):
        """Crawl the target's main page and key API routes to map the attack surface; returns discovered endpoints."""

    async def crawltarget(args: CrawlTargetInput) -> str:
        halted = await eng.refuse_if_halted("crawl_target")
        if halted:
            return halted
        found = []
        async with httpx.AsyncClient(timeout=10.0) as client:
            for path in _RECON_CANDIDATES:
                url = eng.base_url + path
                try:
                    scope_guard(url, cap())
                    r = await client.get(url)
                    found.append({"path": path, "status": r.status_code})
                except ScopeViolationError as e:
                    found.append({"path": path, "blocked": str(e)[:80]})
                except Exception as e:  # network hiccup on one path shouldn't abort the crawl
                    found.append({"path": path, "error": str(e)[:80]})

        await eng.log("tool_result", tool="crawl_target", found=found)
        eng.record_finding(
            type="surface",
            endpoints=[f.get("path") for f in found if f.get("status")],
        )
        lines = "\n".join(f"  {f}" for f in found)
        return (
            f"Discovered endpoints:\n{lines}\n"
            "Candidate vulnerability classes for the Commander to route to specialists:\n"
            "- /rest/products/search?q= flows the q parameter into a SQL query — a SQL injection "
            "candidate (recruit the SQLi Hunter) and a reflected-input / XSS candidate (recruit the XSS Hunter);\n"
            "- /rest/user/login is an authentication endpoint that may be bypassable — an auth candidate "
            "(recruit the Auth Breaker)."
        )

    return [(HttpProbeInput, httpprobe), (CrawlTargetInput, crawltarget)]
