"""Tests for capability-scoped ACLs — intersection, deny-all, and evaluation."""
import pytest

from governance.capability import (
    Capability,
    EmptyScopeError,
    ScopeSpec,
    Target,
    check_capability,
    issue_capability,
    root_capability,
)


def engagement_cap() -> Capability:
    return root_capability("leash-scope-warden", ScopeSpec.of(["localhost"], [3000], ["/"]))


def test_root_capability_allows_in_scope():
    cap = engagement_cap()
    assert check_capability(cap, Target("localhost", 3000, "/rest/products/search"))


def test_root_capability_denies_other_host_port_path():
    cap = engagement_cap()
    assert not check_capability(cap, Target("evil.example.com", 3000, "/"))
    assert not check_capability(cap, Target("localhost", 443, "/"))


def test_issue_narrower_child():
    parent = engagement_cap()
    child = issue_capability(parent, ScopeSpec.of(["localhost"], [3000], ["/rest/products"]))
    assert check_capability(child, Target("localhost", 3000, "/rest/products/search"))
    # The child cannot reach paths outside its restricted prefix.
    assert not check_capability(child, Target("localhost", 3000, "/rest/admin"))


def test_restriction_to_empty_scope_raises():
    parent = engagement_cap()
    with pytest.raises(EmptyScopeError):
        issue_capability(parent, ScopeSpec.of(["localhost"], [9999], ["/"]))  # port not in parent
    with pytest.raises(EmptyScopeError):
        issue_capability(parent, ScopeSpec.of(["evil.example.com"], [3000], ["/"]))  # host mismatch


def test_child_cannot_widen_parent():
    parent = root_capability("w", ScopeSpec.of(["localhost"], [3000], ["/rest"]))
    # Restriction asks for /admin which is outside parent's /rest -> empty path -> deny-all.
    with pytest.raises(EmptyScopeError):
        issue_capability(parent, ScopeSpec.of(["localhost"], [3000], ["/admin"]))


def test_expired_capability_denies():
    cap = root_capability("w", ScopeSpec.of(["localhost"], [3000], ["/"]), expires_at_ms=1_000)
    assert not check_capability(cap, Target("localhost", 3000, "/"), now_ms=2_000)
    assert check_capability(cap, Target("localhost", 3000, "/"), now_ms=500)


def test_glob_matches_single_label():
    cap = root_capability("w", ScopeSpec.of(["*.internal"], [80], ["/"]))
    assert check_capability(cap, Target("app.internal", 80, "/"))
    assert not check_capability(cap, Target("app.prod.internal", 80, "/"))  # '*' is one label


def test_path_boundary_prevents_sibling_prefix_leak():
    # The crown-jewel invariant: a /rest/products cap permits itself and sub-paths,
    # but NEVER a sibling that merely shares the textual prefix.
    cap = root_capability("w", ScopeSpec.of(["localhost"], [3000], ["/rest/products"]))
    assert check_capability(cap, Target("localhost", 3000, "/rest/products"))
    assert check_capability(cap, Target("localhost", 3000, "/rest/products/search"))
    assert not check_capability(cap, Target("localhost", 3000, "/rest/products-evil"))
    assert not check_capability(cap, Target("localhost", 3000, "/rest/productsX"))
