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
    "/rest/chatbot/status",
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

        # Classify the surface from what actually answered (HTTP < 400), so the
        # Commander recruits a specialist only for a class recon really observed —
        # the discovery->recruit loop is driven by live signals, not a static list.
        def _live(prefix: str) -> bool:
            return any(
                isinstance(f.get("status"), int) and f["status"] < 400
                and str(f.get("path", "")).startswith(prefix)
                for f in found
            )

        candidates: list[str] = []
        bullets: list[str] = []
        if _live("/rest/products/search"):
            candidates += ["sqli", "xss"]
            bullets.append(
                "- /rest/products/search?q= flows the q parameter into a SQL query — a SQL injection "
                "candidate (recruit the SQLi Hunter);"
            )
            bullets.append(
                "- /rest/products/search?q= also echoes the q parameter into the HTML response — a "
                "reflected-input / XSS candidate (recruit the XSS Hunter);"
            )
        if _live("/rest/user/login"):
            candidates.append("auth")
            bullets.append(
                "- /rest/user/login is an authentication endpoint that may be bypassable — an auth "
                "candidate (recruit the Auth Breaker);"
            )
        if _live("/rest/chatbot"):
            candidates.append("prompt_injection")
            bullets.append(
                "- /rest/chatbot/* answered — an LLM-backed support endpoint that may follow injected "
                "instructions — a prompt-injection candidate (recruit the Prompt-Injection Tester);"
            )
        if _live("/api/Users"):
            candidates.append("sensitive_data")
            bullets.append(
                "- /api/Users returned account records and may over-expose PII/PHI — a sensitive-data-"
                "exposure candidate (recruit the Data Exposure Sentinel);"
            )

        # The classified candidates ride into the audit chain on the surface finding,
        # so the discovery->recruit mapping is machine-readable from the sealed bundle.
        eng.record_finding(
            type="surface",
            endpoints=[f.get("path") for f in found if f.get("status")],
            candidates=candidates,
        )
        lines = "\n".join(f"  {f}" for f in found)
        classes = (
            "Candidate vulnerability classes (observed live) for the Commander to route to specialists:\n"
            + "\n".join(bullets)
            if bullets
            else "No classifiable attack surface answered on this pass."
        )
        return f"Discovered endpoints:\n{lines}\n{classes}"

    return [(HttpProbeInput, httpprobe), (CrawlTargetInput, crawltarget)]
