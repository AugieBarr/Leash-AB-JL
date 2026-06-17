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


def narrowed_cap():
    return root_capability("eng", ScopeSpec.of(["localhost"], [3000], ["/rest/products"]))


def test_path_prefix_boundary_blocks_sibling():
    # A /rest/products cap must NOT leak to a sibling whose name merely shares the prefix.
    cap = narrowed_cap()
    with pytest.raises(ScopeViolationError):
        scope_guard("http://localhost:3000/rest/products-evil", cap)
    with pytest.raises(ScopeViolationError):
        scope_guard("http://localhost:3000/rest/productsX", cap)


def test_path_prefix_allows_self_and_subpath():
    cap = narrowed_cap()
    assert scope_guard("http://localhost:3000/rest/products", cap).path == "/rest/products"
    assert scope_guard("http://localhost:3000/rest/products/search", cap).path == "/rest/products/search"


def test_dot_dot_traversal_blocked():
    # /rest/products/../admin normalizes to /admin, which is out of the narrowed scope.
    cap = narrowed_cap()
    with pytest.raises(ScopeViolationError):
        scope_guard("http://localhost:3000/rest/products/../admin", cap)


def test_parse_target_normalizes_dot_dot():
    # /rest/products/.. -> /rest, then /admin -> /rest/admin (still outside a /rest/products cap)
    assert parse_target("http://localhost:3000/rest/products/../admin").path == "/rest/admin"
    assert parse_target("http://localhost:3000/rest/products/../../admin").path == "/admin"
    assert parse_target("http://localhost:3000/a//b/./c").path == "/a/b/c"


def test_percent_encoded_traversal_decoded_and_blocked():
    # The server URL-decodes the path, so an ENCODED traversal must be decoded
    # before the prefix check or a /rest/products cap leaks to /rest/admin.
    cap = narrowed_cap()
    with pytest.raises(ScopeViolationError):
        scope_guard("http://localhost:3000/rest/products/%2e%2e/admin", cap)
    with pytest.raises(ScopeViolationError):
        scope_guard("http://localhost:3000/rest/products%2f..%2fadmin", cap)


def test_parse_target_percent_decodes_path():
    assert parse_target("http://localhost:3000/rest/products/%2e%2e/admin").path == "/rest/admin"
    assert parse_target("http://localhost:3000/rest/products%2f..%2fadmin").path == "/rest/admin"
    # Mixed-case encoding decodes too.
    assert parse_target("http://localhost:3000/rest/%2E%2E/admin").path == "/admin"


def test_double_encoded_traversal_decoded_to_fixed_point_and_blocked():
    # A server that URL-decodes twice would resolve %252e%252e -> %2e%2e -> '..'.
    # The guard decodes to a fixed point, so the bypass fails closed regardless of
    # the target's decode depth.
    cap = narrowed_cap()
    assert parse_target("http://localhost:3000/rest/products/%252e%252e/admin").path == "/rest/admin"
    with pytest.raises(ScopeViolationError):
        scope_guard("http://localhost:3000/rest/products/%252e%252e/admin", cap)
    with pytest.raises(ScopeViolationError):
        scope_guard("http://localhost:3000/rest/products/%25252e%25252e/admin", cap)
