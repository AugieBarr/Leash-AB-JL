"""Tests for the fail-closed scope guard."""
import pytest

from governance.capability import ScopeSpec, root_capability
from governance.scope_guard import ScopeViolationError, parse_target, scope_guard


def engagement_cap():
    return root_capability("eng", ScopeSpec.of(["localhost"], [3000], ["/"]))


def test_in_scope_url_passes():
    cap = engagement_cap()
    t = scope_guard("http://localhost:3000/rest/products/search", cap)
    assert t.host == "localhost" and t.port == 3000


def test_bare_host_port_passes():
    cap = engagement_cap()
    assert scope_guard("localhost:3000", cap).port == 3000


def test_out_of_scope_host_blocked():
    cap = engagement_cap()
    with pytest.raises(ScopeViolationError):
        scope_guard("http://google.com/search", cap)


def test_out_of_scope_port_blocked():
    cap = engagement_cap()
    with pytest.raises(ScopeViolationError):
        scope_guard("http://localhost:8080/", cap)


def test_empty_host_fails_closed():
    cap = engagement_cap()
    with pytest.raises(ScopeViolationError):
        scope_guard("http://", cap)


def test_sqlmap_injection_marker_stripped():
    cap = engagement_cap()
    # sqlmap appends a '*' injection marker; the guard must not block on it.
    t = scope_guard("http://localhost:3000/rest/products/search?q=*", cap)
    assert t.host == "localhost"


def test_parse_target_defaults_https_port():
    assert parse_target("https://localhost/").port == 443
