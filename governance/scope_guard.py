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
    # Percent-DECODE, then normalize away '..' and duplicate slashes BEFORE the
    # prefix check. The target server URL-decodes the path and resolves '..'
    # itself, so a narrowed /rest/products cap must not be escapable by *encoding*
    # the traversal:
    #     /rest/products/%2e%2e/admin   (%2e%2e -> '..')
    #     /rest/products%2f..%2fadmin   (%2f    -> '/')
    # both resolve to /rest/admin and must fail closed. We decode once — matching
    # a server that URL-decodes the path a single time (double-encoding like
    # %252e stays literal here, exactly as such a server would see it).
    decoded = unquote((parts.path or "/").replace("*", ""))
    path = posixpath.normpath(decoded)
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
