"""Offline bundle verifier CLI.

    python -m governance.verify <engagement>_bundle.tar.gz

Re-checks chain linkage + every Ed25519 signature from the tarball alone, with
no live ledger and no private key. This is the live-demo "anyone can verify it"
moment.
"""
from __future__ import annotations

import sys

from governance.bundle import verify_bundle


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print("usage: python -m governance.verify <bundle.tar.gz>")
        return 2

    result = verify_bundle(argv[0])
    print(result.detail)
    if result.manifest:
        m = result.manifest
        print(f"  engagement: {m.get('engagement_id')}   target: {m.get('target')}")
        print(f"  chain tail: {m.get('chain_tail_hash')}")
        print(f"  findings:   {len(m.get('findings') or [])}")
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
