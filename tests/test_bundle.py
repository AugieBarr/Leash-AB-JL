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


def _repack(bundle, members):
    with tarfile.open(bundle, "w:gz") as tar:
        for name, data in members.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))


def _members(bundle):
    with tarfile.open(bundle, "r:gz") as tar:
        return {m.name: tar.extractfile(m).read() for m in tar.getmembers()}


async def test_seal_and_verify(tmp_path):
    await _seed(tmp_path, "demo")
    bundle = export_bundle("demo", root=tmp_path, target="localhost:3000", findings=[{"type": "sqli"}])
    result = verify_bundle(bundle)
    assert result.ok, result.detail
    assert "2 events" in result.detail
    assert result.manifest["target"] == "localhost:3000"
    assert result.manifest["event_count"] == 2
    # The bundle ships a detached manifest signature (the truncation defence).
    assert "manifest.sig" in _members(bundle)


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


async def test_forged_manifest_field_fails_signature(tmp_path):
    # Leave the signed ndjson untouched but forge the manifest's advertised tail.
    # The detached manifest signature must catch any edit to the manifest bytes.
    await _seed(tmp_path, "demo4")
    bundle = export_bundle("demo4", root=tmp_path)

    members = _members(bundle)
    manifest = json.loads(members["manifest.json"])
    manifest["chain_tail_hash"] = "00" * 32  # forge the advertised tail
    members["manifest.json"] = json.dumps(manifest, indent=2).encode()
    _repack(bundle, members)

    result = verify_bundle(bundle)
    assert not result.ok
    assert "signature invalid" in result.detail


async def test_truncated_bundle_fails(tmp_path):
    # The P1 attack: drop trailing events and re-derive a *consistent* shorter
    # manifest (event_count + chain_tail_hash recomputable from the public key),
    # keeping the original signature. Without a signed manifest this verified clean;
    # the manifest signature now defeats it. Also covers truncation that leaves the
    # original manifest in place (caught by the tail cross-check).
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    from governance.audit_ledger import verify_ndjson

    led = await _seed(tmp_path, "demo5")
    await led.append("approval", json.dumps({"endpoint": "/rest/products/search"}))
    await led.append("kill_switch", json.dumps({"reason": "operator halt", "halted": True}))
    bundle = export_bundle("demo5", root=tmp_path)
    pubkey = Ed25519PublicKey.from_public_bytes(led.public_key_bytes())

    base = _members(bundle)
    full_lines = base["audit.ndjson"].decode().splitlines()
    truncated_lines = full_lines[:-2]  # hide the approval + kill_switch tail

    # (a) attacker adjusts the manifest to match the truncated chain, keeps old sig.
    forged = json.loads(base["manifest.json"])
    forged["event_count"] = len(truncated_lines)
    forged["chain_tail_hash"] = verify_ndjson(truncated_lines, pubkey).tail_hash
    members_a = dict(base)
    members_a["audit.ndjson"] = ("\n".join(truncated_lines) + "\n").encode()
    members_a["manifest.json"] = json.dumps(forged, indent=2).encode()  # sig now stale
    _repack(bundle, members_a)
    assert not verify_bundle(bundle).ok  # caught by the manifest signature

    # (b) attacker truncates the ndjson but leaves the original manifest + sig.
    bundle2 = export_bundle("demo5", root=tmp_path)  # re-seal a clean bundle
    base2 = _members(bundle2)
    members_b = dict(base2)
    members_b["audit.ndjson"] = ("\n".join(base2["audit.ndjson"].decode().splitlines()[:-2]) + "\n").encode()
    _repack(bundle2, members_b)
    assert not verify_bundle(bundle2).ok  # caught by the tail/count cross-check
