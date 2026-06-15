"""Sealed audit bundle — the regulator-ready artifact for a closed engagement.

``export_bundle`` verifies the chain, refuses to seal a tampered one, then packs
the NDJSON ledger + a manifest (which carries the Ed25519 public key, tail hash,
and event count) into a portable ``<id>_bundle.tar.gz`` with a sidecar SHA-256.
``verify_bundle`` re-checks everything from the tarball alone — no live ledger,
no private key — so any third party can confirm the trail was not altered.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import tarfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from governance.audit_ledger import AuditLedger, verify_ndjson


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _add_bytes(tar: tarfile.TarFile, name: str, data: bytes) -> None:
    info = tarfile.TarInfo(name=name)
    info.size = len(data)
    info.mtime = 0  # deterministic
    tar.addfile(info, io.BytesIO(data))


def _count_events(ndjson_text: str) -> int:
    """Count non-blank NDJSON lines — the canonical 'how many events' measure."""
    return sum(1 for line in ndjson_text.splitlines() if line.strip())


def export_bundle(
    engagement_id: str,
    *,
    root: str | os.PathLike = "engagements",
    target: Optional[str] = None,
    findings: Optional[list] = None,
    now_ms: Optional[int] = None,
) -> Path:
    """Verify, then seal the engagement's ledger into a portable bundle. Raises
    ValueError if the chain does not verify (never seals a tampered trail)."""
    ledger = AuditLedger(engagement_id, root=root)
    result = ledger.verify_chain()
    if not result.ok:
        raise ValueError(f"refusing to seal a tampered chain: {result.detail}")

    ndjson_bytes = ledger.path.read_bytes()
    event_count = _count_events(ndjson_bytes.decode("utf-8"))
    manifest = {
        "engagement_id": engagement_id,
        "target": target,
        "sealed_at_ms": now_ms if now_ms is not None else int(time.time() * 1000),
        "event_count": event_count,
        "chain_tail_hash": ledger.tail_hash_hex,
        "pubkey_ed25519_b64": base64.b64encode(ledger.public_key_bytes()).decode("ascii"),
        "findings": findings or [],
    }
    manifest_bytes = json.dumps(manifest, indent=2).encode("utf-8")

    bundle_path = ledger.dir / f"{engagement_id}_bundle.tar.gz"
    with tarfile.open(bundle_path, "w:gz") as tar:
        _add_bytes(tar, "audit.ndjson", ndjson_bytes)
        _add_bytes(tar, "manifest.json", manifest_bytes)

    sha = _sha256_file(bundle_path)
    (ledger.dir / f"{engagement_id}_bundle.sha256").write_text(f"{sha}  {bundle_path.name}\n")
    return bundle_path


@dataclass(frozen=True)
class BundleVerifyResult:
    ok: bool
    detail: str
    manifest: Optional[dict] = None

    def __bool__(self) -> bool:
        return self.ok


def verify_bundle(bundle_path: str | os.PathLike) -> BundleVerifyResult:
    """Verify a sealed bundle offline: chain linkage + signatures + manifest cross-check."""
    bundle_path = Path(bundle_path)
    with tarfile.open(bundle_path, "r:gz") as tar:
        names = set(tar.getnames())
        if not {"manifest.json", "audit.ndjson"} <= names:
            return BundleVerifyResult(False, "bundle missing manifest.json or audit.ndjson")
        manifest = json.loads(tar.extractfile("manifest.json").read().decode("utf-8"))
        ndjson_text = tar.extractfile("audit.ndjson").read().decode("utf-8")

    # These three fields are load-bearing for the cross-check below; a missing one
    # is a malformed bundle, not a value mismatch — surface that distinctly.
    required = {"pubkey_ed25519_b64", "chain_tail_hash", "event_count"}
    missing = required - manifest.keys()
    if missing:
        return BundleVerifyResult(
            False, f"malformed manifest: missing {', '.join(sorted(missing))}", manifest
        )

    pubkey = Ed25519PublicKey.from_public_bytes(
        base64.b64decode(manifest["pubkey_ed25519_b64"])
    )

    result = verify_ndjson(ndjson_text.splitlines(), pubkey)

    if not result.ok:
        return BundleVerifyResult(False, result.detail, manifest)

    # Cross-check the manifest's advertised tail/count against what the chain
    # actually re-derives — otherwise a reader trusting manifest['chain_tail_hash']
    # would be trusting an unverified, bundle-local value.
    if result.tail_hash != manifest["chain_tail_hash"]:
        return BundleVerifyResult(
            False,
            f"chain tail mismatch: manifest says {manifest['chain_tail_hash']}, "
            f"recomputed {result.tail_hash}",
            manifest,
        )

    count = _count_events(ndjson_text)
    if count != manifest["event_count"]:
        return BundleVerifyResult(
            False,
            f"event_count mismatch: manifest says {manifest['event_count']}, found {count}",
            manifest,
        )
    return BundleVerifyResult(
        True, f"Chain OK — {count} events, no tampering detected", manifest
    )
