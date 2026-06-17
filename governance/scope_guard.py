"""Fail-closed scope chokepoint — clean-room MIT port of DiogenesCore.Egress.

Every worker tool call routes a target URL/host through ``scope_guard`` before
any subprocess or network call executes. An empty or unparseable host fails
closed (raises). A target outside the capability's scope raises
``ScopeViolationError`` — callers do not catch it in normal flow; it is meant to
abort the tool call.
"""
from __future__ import annotations

import posixpath
from typing import Optional
from urllib.parse import unquote, urlsplit

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
    # Percent-DECODE to a fixed point, then normalize away '..' and duplicate
    # slashes BEFORE the prefix check. The target server URL-decodes the path and
    # resolves '..' itself, so a narrowed /rest/products cap must not be escapable
    # by *encoding* the traversal — at any decode depth:
    #     /rest/products/%2e%2e/admin      (%2e%2e   -> '..')
    #     /rest/products%2f..%2fadmin       (%2f      -> '/')
    #     /rest/products/%252e%252e/admin   (%252e%252e -> %2e%2e -> '..')
    # all resolve to /rest/admin and must fail closed. Decoding repeatedly (bounded)
    # makes the guard independent of how many times the target decodes — erring
    # toward over-decoding is the fail-closed choice for a security boundary.
    raw = (parts.path or "/").replace("*", "")
    for _ in range(8):  # converges in 1-2 for any realistic input; bounded for safety
        decoded = unquote(raw)
        if decoded == raw:
            break
        raw = decoded
    path = posixpath.normpath(raw)
    if not path.startswith("/"):
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
