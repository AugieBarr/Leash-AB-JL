"""Recon http_probe must fail closed when the target is out of the scout's scope.

Deterministic — the scope guard raises before any network call, so this needs
no live target.
"""
from governance.capability import ScopeSpec, issue_capability
from swarm.engagement import open_engagement
from tools.recon_tools import recon_tools


def _pair(eng, name):
    return next((m, h) for m, h in recon_tools(eng) if m.__name__ == name)


async def test_http_probe_blocked_out_of_scope(tmp_path):
    eng = open_engagement("t-recon", "localhost", 3000, root=str(tmp_path))
    # Scout scoped to /rest only — probing "/" (the parent) is out of scope.
    eng.capabilities["leash-recon-scout"] = issue_capability(
        eng.root_cap, ScopeSpec.of(["localhost"], [3000], ["/rest"])
    )
    model, handler = _pair(eng, "HttpProbeInput")
    out = await handler(model(path="/"))
    assert "BLOCKED" in out
    assert eng.findings == []
