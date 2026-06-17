"""Data Exposure Sentinel tools — confirm sensitive-data (PII/PHI) exposure on
in-scope endpoints.

A governed compliance/DLP specialist in the same honest mold as the SQLi/XSS/Auth
tools: it *detects* whether an endpoint leaks sensitive data it should not, and
reports the TYPE and COUNT of each pattern found — never the raw values, so a
compliance test never itself becomes a data-harvesting step. This is OWASP
A01/A04 sensitive-data-exposure / DLP testing for HIPAA/PCI-style programs.

Governed exactly like the other offensive tools: refused when halted, bounded by
the scope guard before the gate is ever opened, and blocked behind the
code-enforced human approval gate before any request leaves.
"""
from __future__ import annotations

import re

import httpx
from pydantic import BaseModel, Field

from governance.scope_guard import ScopeViolationError, scope_guard
from swarm.control_channel import enforce_gate
from tools._subprocess import ensure_leading_slash

_GATE_DENIED = (
    "BLOCKED: human approval required before exploitation. The operator halted "
    "or did not approve this action at the Control Center gate."
)

# Patterns that should not appear in a response not meant to expose them. We report
# the TYPE and COUNT of each hit, never the matched value — a DLP test must not
# itself become a data-exfiltration step.
# All patterns use a non-capturing group + word boundaries so re.findall returns
# full matches (counted, never stored) and email-shaped substrings inside base64
# blobs or bearer tokens don't trip a false positive.
_PATTERNS = {
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    "us_ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "credit_card": re.compile(r"\b(?:\d{4}[ -]?){3}\d{4}\b"),
    "phi_keyword": re.compile(r"\b(?:diagnosis|patient|medical record|prescription|ICD-?10)\b", re.I),
}


def exposure_tools(eng, *, gate_timeout: float = 600.0, gate_poll: float = 0.4):
    cap = lambda: eng.cap_for("leash-data-sentinel")  # noqa: E731 (terse local, mirrors sqli_tools)

    async def _gate(tool: str, endpoint: str, detail: str) -> bool:
        """Pass iff the operator has approved this endpoint; otherwise open the
        Control Center gate and block on their decision — enforced in code."""
        if eng.is_approved(endpoint):
            return True
        return await enforce_gate(
            eng, tool=tool, endpoint=endpoint, detail=detail, timeout=gate_timeout, poll=gate_poll
        )

    class ManualDataExposureProbeInput(BaseModel):
        """Confirm sensitive-data (PII/PHI) exposure on an in-scope endpoint by fetching it and scanning the response for sensitive patterns; reports the type and count of any leak, never the raw values."""

        path: str = Field(
            default="/api/Users",
            description="Endpoint path to inspect for sensitive-data exposure, e.g. /api/Users (returns account records unauthenticated on Juice Shop). Note: the probe is unauthenticated, so an endpoint that only leaks PII behind a session may return 401/403 and read as not-confirmed.",
        )

    async def manualdataexposureprobe(args: ManualDataExposureProbeInput) -> str:
        halted = await eng.refuse_if_halted("manual_data_exposure_probe")
        if halted:
            return halted
        base = ensure_leading_slash(args.path)
        # Scope is checked BEFORE the gate (mirrors sqli_tools): an out-of-scope
        # reach fails closed by construction without ever bothering the operator.
        url = eng.base_url + base
        try:
            scope_guard(url, cap())
        except ScopeViolationError as e:
            await eng.log("error", tool="manual_data_exposure_probe", path=base, blocked=str(e))
            return f"BLOCKED by scope guard: {e}"
        if not await _gate(
            "manual_data_exposure_probe", base,
            "sensitive-data (PII/PHI) exposure scan on the endpoint response",
        ):
            return _GATE_DENIED

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)

        body = resp.text or ""
        # Count hits per type; NEVER record the matched values (responsible DLP test).
        hits = {name: len(rx.findall(body)) for name, rx in _PATTERNS.items()}
        hits = {name: n for name, n in hits.items() if n}
        # Only a SUCCESS response is real exposure: a 403/500 error page can carry an
        # email or the word "patient" in its body or a stack trace — that is an error,
        # not a leak, and must not become a sensitive_data_exposure finding.
        ok_status = resp.status_code < 400
        confirmed = bool(hits) and ok_status

        await eng.log(
            "tool_result",
            tool="manual_data_exposure_probe",
            path=base,
            status=resp.status_code,
            exposed_types=sorted(hits),
            exposed_counts=hits,
            confirmed=confirmed,
        )
        if confirmed:
            summary = ", ".join(f"{n}x {name}" for name, n in sorted(hits.items()))
            eng.record_finding(
                type="sensitive_data_exposure",
                endpoint=base,
                severity="high",
                evidence=f"response exposed sensitive patterns ({summary}); raw values redacted",
            )
            return (
                f"[VULNERABLE] {base} exposes sensitive data in its response — pattern hits: "
                f"{summary} (raw values redacted). OWASP A01/A04 sensitive-data exposure."
            )
        if hits and not ok_status:
            return (
                f"[not confirmed] {base}: sensitive-shaped patterns appeared only in a non-success "
                f"response (HTTP {resp.status_code}) — treated as an error body, not a leak. No finding."
            )
        return (
            f"[not confirmed] {base}: no sensitive-data patterns found in the response "
            f"(HTTP {resp.status_code})."
        )

    return [(ManualDataExposureProbeInput, manualdataexposureprobe)]
