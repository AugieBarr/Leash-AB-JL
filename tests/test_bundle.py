"""Tests for sealing and verifying audit bundles."""
import io
import json
import tarfile

import pytest

from governance.audit_ledger import AuditLedger
from governance.bundle import export_bundle, verify_bundle


async def _seed(root, eid):
    led = AuditLedger(eid, root=root)
    await led.append("engagement_open", json.dumps({"engagement": eid}))
    await led.append("tool_result", json.dumps({"vuln": "sqli", "endpoint": "/rest/products/search"}))
    return led


async def test_seal_and_verify(tmp_path):
    await _seed(tmp_path, "demo")
    bundle = export_bundle("demo", root=tmp_path, target="localhost:3000", findings=[{"type": "sqli"}])
    result = verify_bundle(bundle)
    assert result.ok, result.detail
    assert "2 events" in result.detail
    assert result.manifest["target"] == "localhost:3000"
    assert result.manifest["event_count"] == 2


async def test_tampered_bundle_fails(tmp_path):
    await _seed(tmp_path, "demo2")
    bundle = export_bundle("demo2", root=tmp_path)

    # Rewrite the audit.ndjson inside the sealed tarball.
    with tarfile.open(bundle, "r:gz") as tar:
        members = {m.name: tar.extractfile(m).read() for m in tar.getmembers()}
    lines = members["audit.ndjson"].decode().splitlines()
    rec = json.loads(lines[0])
    rec["payload"] = json.dumps({"engagement": "FORGED"})
    lines[0] = json.dumps(rec)
    members["audit.ndjson"] = ("\n".join(lines) + "\n").encode()
    with tarfile.open(bundle, "w:gz") as tar:
        for name, data in members.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))

    assert not verify_bundle(bundle).ok


async def test_export_refuses_tampered_ledger(tmp_path):
    led = await _seed(tmp_path, "demo3")
    lines = led.path.read_text().splitlines()
    rec = json.loads(lines[0])
    rec["payload"] = json.dumps({"engagement": "FORGED"})
    lines[0] = json.dumps(rec)
    led.path.write_text("\n".join(lines) + "\n")

    with pytest.raises(ValueError):
        export_bundle("demo3", root=tmp_path)


async def test_tampered_manifest_tail_fails(tmp_path):
    # Leave the signed ndjson untouched but forge the manifest's advertised tail.
    # verify_bundle must catch the mismatch — a reader trusting manifest fields
    # cannot be handed an unverified value.
    await _seed(tmp_path, "demo4")
    bundle = export_bundle("demo4", root=tmp_path)

    with tarfile.open(bundle, "r:gz") as tar:
        members = {m.name: tar.extractfile(m).read() for m in tar.getmembers()}
    manifest = json.loads(members["manifest.json"])
    manifest["chain_tail_hash"] = "00" * 32  # forge the advertised tail
    members["manifest.json"] = json.dumps(manifest, indent=2).encode()
    with tarfile.open(bundle, "w:gz") as tar:
        for name, data in members.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))

    result = verify_bundle(bundle)
    assert not result.ok
    assert "tail mismatch" in result.detail
