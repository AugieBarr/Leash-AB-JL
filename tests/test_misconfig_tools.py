"""Tests for the misconfig/exposure tools — the deterministic scope-guard path.

The live positive path (real headers/exposure on Juice Shop) is covered by
scripts/offline_demo.py, mirroring the recon/sqli tools. Here we assert the
governance behaviour without any network: when the owner's capability does not
cover a path, the exposure probe must fail closed (report it scope-guarded) and
must NOT record a finding — fail-closed is the whole point.
"""
from governance.capability import ScopeSpec, issue_capability
from swarm.engagement import open_engagement
from tools.misconfig_tools import misconfig_tools


def _pair(eng, name):
    return next((m, h) for m, h in misconfig_tools(eng) if m.__name__ == name)


async def test_exposure_probe_fails_closed_when_out_of_scope(tmp_path):
    eng = open_engagement("t-misconfig", "localhost", 3000, root=str(tmp_path))
    # Recon scout scoped to ONLY /rest/products — /ftp and /rest/admin are out of scope.
    eng.capabilities["leash-recon-scout"] = issue_capability(
        eng.root_cap, ScopeSpec.of(["localhost"], [3000], ["/rest/products"])
    )
    model, handler = _pair(eng, "ExposureProbeInput")

    out = await handler(model())

    assert "scope-guarded" in out
    assert "/ftp" in out
    assert "/rest/admin/application-version" in out
    # Fail-closed must never manufacture a finding from a blocked path.
    assert eng.findings == []


async def test_exposure_tool_set_shape(tmp_path):
    eng = open_engagement("t-misconfig-shape", "localhost", 3000, root=str(tmp_path))
    names = {m.__name__ for m, _ in misconfig_tools(eng)}
    assert names == {"SecurityHeadersProbeInput", "ExposureProbeInput"}
