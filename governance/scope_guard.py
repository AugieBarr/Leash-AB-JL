"""Fail-closed scope chokepoint — clean-room MIT port of DiogenesCore.Egress.

Every worker tool call routes a target URL/host through ``scope_guard`` before
any subprocess or network call executes. An empty or unparseable host fails
closed (raises). A target outside the capability's scope raises
``ScopeViolationError`` — callers do not catch it in normal flow; it is meant to
abort the tool call.
"""
from __future__ import annotations

from typing import Optional
from urllib.parse import urlsplit

from governance.capability import Capability, Target, check_capability


class ScopeViolationError(Exception):
    """Raised when a tool targets a host/port/path outside the engagement scope."""


def parse_target(url: str) -> Target:
    """Parse a bare ``host[:port][/path]`` or a full URL into a Target. Strips
    sqlmap-style ``*`` injection markers from the path before extraction."""
    raw = url if "://" in url else "http://" + url
    parts = urlsplit(raw)
    host = parts.hostname or ""
    if parts.port is not None:
        port = parts.port
    else:
        port = 443 if parts.scheme == "https" else 80
    path = (parts.path or "/").replace("*", "")
    if not path:
        path = "/"
    return Target(host=host, port=port, path=path)


def scope_guard(url: str, cap: Capability, *, now_ms: Optional[int] = None) -> Target:
    """Authorize a target against ``cap`` or raise. Returns the parsed Target on success."""
    target = parse_target(url)
    if not target.host:
        raise ScopeViolationError(f"unparseable or empty host in target: {url!r}")
    if not check_capability(cap, target, now_ms=now_ms):
        raise ScopeViolationError(
            f"out of scope: {target.host}:{target.port}{target.path} "
            f"is not permitted by capability {cap.id}"
        )
    return target
