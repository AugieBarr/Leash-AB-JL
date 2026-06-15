"""Capability-scoped ACLs — clean-room MIT port of Hermes.Themis (Elixir).

A capability grants an agent access to a scope (hosts/ports/paths). A parent
capability can derive a strictly-narrower child via ``issue_capability`` (set
intersection); if any field intersects to empty the result is a deny-all, which
is surfaced as ``EmptyScopeError`` so a caller cannot accidentally tunnel a
no-op capability. ``check_capability`` is the evaluator: expiry -> empty-scope ->
host -> port -> path, default-deny throughout.
"""
from __future__ import annotations

import re
import secrets
import time
from dataclasses import dataclass
from typing import Optional


class EmptyScopeError(Exception):
    """Raised when a restriction intersects its parent to an empty (deny-all) scope."""


@dataclass(frozen=True)
class ScopeSpec:
    hosts: tuple[str, ...]          # glob patterns; '*' matches a single DNS label
    ports: tuple[int, ...]
    paths: tuple[str, ...] = ("/",)  # path prefixes; "/" or "*" covers all paths

    @staticmethod
    def of(hosts, ports, paths=("/",)) -> "ScopeSpec":
        return ScopeSpec(tuple(hosts), tuple(int(p) for p in ports), tuple(paths))


@dataclass(frozen=True)
class Capability:
    id: str
    agent_id: str
    scope: ScopeSpec
    parent_id: Optional[str] = None
    issued_at_ms: int = 0
    expires_at_ms: Optional[int] = None  # None => no expiry (engagement-scoped)


@dataclass(frozen=True)
class Target:
    host: str
    port: int
    path: str = "/"


def _now_ms() -> int:
    return int(time.time() * 1000)


def _fresh_id() -> str:
    return secrets.token_hex(16)


def _glob_match(glob: str, host: str) -> bool:
    # '*' matches exactly one DNS label (no dots), mirroring Hermes.Themis.glob_match.
    pattern = "^" + re.escape(glob).replace(r"\*", r"[^.]+") + "$"
    return re.match(pattern, host) is not None


def _host_match(globs, host: str) -> bool:
    return any(_glob_match(g, host) for g in globs)


def _path_match(prefixes, path: str) -> bool:
    # Boundary-aware prefix match: a cap for "/rest/products" must match
    # "/rest/products" and "/rest/products/search" but NOT "/rest/products-evil"
    # or "/rest/productsX" — a bare str.startswith would leak those.
    def _one(pref: str, path: str) -> bool:
        if pref in ("/", "*"):
            return True
        return path == pref or path.startswith(pref.rstrip("/") + "/")

    return any(_one(pref, path) for pref in prefixes)


def _empty(scope: ScopeSpec) -> bool:
    return not scope.hosts or not scope.ports or not scope.paths


def root_capability(
    agent_id: str, scope: ScopeSpec, *, expires_at_ms: Optional[int] = None
) -> Capability:
    """Mint a top-level engagement capability (no parent)."""
    return Capability(
        id=_fresh_id(),
        agent_id=agent_id,
        scope=scope,
        parent_id=None,
        issued_at_ms=_now_ms(),
        expires_at_ms=expires_at_ms,
    )


def issue_capability(
    parent: Capability, restriction: ScopeSpec, *, agent_id: Optional[str] = None
) -> Capability:
    """Derive a child capability = parent ∩ restriction. Raises EmptyScopeError
    if any field intersects to empty (the deny-all sentinel)."""
    child_hosts = tuple(h for h in restriction.hosts if _host_match(parent.scope.hosts, h))
    child_ports = tuple(p for p in restriction.ports if p in parent.scope.ports)
    child_paths = tuple(pp for pp in restriction.paths if _path_match(parent.scope.paths, pp))

    if not child_hosts or not child_ports or not child_paths:
        raise EmptyScopeError(
            f"restriction intersects to empty scope under parent {parent.id}"
        )

    return Capability(
        id=_fresh_id(),
        agent_id=agent_id or parent.agent_id,
        scope=ScopeSpec(child_hosts, child_ports, child_paths),
        parent_id=parent.id,
        issued_at_ms=_now_ms(),
        expires_at_ms=parent.expires_at_ms,
    )


def check_capability(cap: Capability, target: Target, *, now_ms: Optional[int] = None) -> bool:
    """Default-deny evaluator. Order: expiry, empty-scope, host, port, path."""
    now = now_ms if now_ms is not None else _now_ms()
    if cap.expires_at_ms is not None and now > cap.expires_at_ms:
        return False
    scope = cap.scope
    if _empty(scope):
        return False
    if not _host_match(scope.hosts, target.host):
        return False
    if target.port not in scope.ports:
        return False
    if not _path_match(scope.paths, target.path):
        return False
    return True
