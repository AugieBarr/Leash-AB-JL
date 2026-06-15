"""Tamper-evidence demo — prove the audit trail cannot be rewritten undetected.

Forks a sealed engagement into a throwaway copy, flips ONE field in ONE
already-signed event, and re-verifies. The Ed25519 signature was computed over
the original payload, so the mutated event fails verification — and the chain
names exactly which sequence number was touched. Point the live viewer at the
forked engagement and it renders that event red with a TAMPERED badge.

This is the visible proof of the governance thesis: anyone can read the trail,
but no one can rewrite history without it being caught — and detection needs only
the public key shipped in the bundle, never the private key.

    python scripts/offline_demo.py                      # produce a clean sealed engagement
    python scripts/tamper_demo.py                       # fork it, alter one event, get caught
    python -m viewer.viewer --engagement tamper-demo    # watch it render red
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from governance.audit_ledger import AuditLedger  # noqa: E402

ENGAGEMENTS = Path("engagements")


def _pick_and_mutate(records: list[dict]) -> tuple[int, str]:
    """Flip the most incriminating field we can find, in place. Returns (seq, note).

    We re-serialize the payload with the same options the ledger used
    (``json.dumps(..., sort_keys=True)``), so the ONLY difference from the
    original is the single value we changed — which is exactly the tamper that
    the signature over the original payload will catch.
    """
    # Prefer erasing the SQL-injection finding — the most intuitive "hide the
    # evidence" tamper — then fall back to forging the human approval record.
    for rec in records:
        payload = json.loads(rec["payload"])
        if rec["kind"] == "tool_result" and payload.get("injectable") is True:
            payload["injectable"] = False
            rec["payload"] = json.dumps(payload, sort_keys=True)
            return rec["seq"], "injectable  true → false   (attacker erases the SQL-injection finding)"
    for rec in records:
        payload = json.loads(rec["payload"])
        if rec["kind"] == "approval" and payload.get("decision"):
            was = payload["decision"]
            payload["decision"] = "denied"
            rec["payload"] = json.dumps(payload, sort_keys=True)
            return rec["seq"], f'decision  "{was}" → "denied"   (forging the operator record)'
    # Fallback: perturb the first event's payload so the demo always lands.
    rec = records[1] if len(records) > 1 else records[0]
    payload = json.loads(rec["payload"])
    payload["_tampered"] = True
    rec["payload"] = json.dumps(payload, sort_keys=True)
    return rec["seq"], "payload altered (a field was added after signing)"


def main() -> int:
    p = argparse.ArgumentParser(description="Fork a sealed engagement, alter one event, and get caught.")
    p.add_argument("--source", default="offline-demo", help="Engagement to fork (must already exist).")
    p.add_argument("--dest", default="tamper-demo", help="Throwaway forked engagement to mutate.")
    args = p.parse_args()

    src = ENGAGEMENTS / args.source
    dst = ENGAGEMENTS / args.dest
    if not (src / "audit.ndjson").exists():
        print(f"[!] No sealed engagement at {src}. Run: python scripts/offline_demo.py")
        return 2

    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)  # carries the key file, so the public key still derives
    print(f"[*] Forked {args.source} → {args.dest} (a throwaway copy of the sealed trail)")

    ndjson = dst / "audit.ndjson"
    records = [json.loads(ln) for ln in ndjson.read_text(encoding="utf-8").splitlines() if ln.strip()]
    seq, note = _pick_and_mutate(records)
    ndjson.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    print(f"[!] Altered event #{seq}: {note}")

    # Re-verify with the engagement's own public key — exactly what the offline
    # verifier and the live viewer do. The mutated payload no longer matches its
    # signature, so the chain pinpoints the tampered event.
    result = AuditLedger(args.dest).verify_chain()
    print(f"[verify] {'TAMPERED — ' if not result.ok else ''}{result.detail}")
    if not result.ok:
        print(
            "         The Ed25519 signature was computed over the ORIGINAL payload; the\n"
            "         mutated payload no longer matches. Caught with the public key alone."
        )
    print(f"\nWatch it light up red:  python -m viewer.viewer --engagement {args.dest}")
    return 0 if not result.ok else 1  # success == the tamper WAS detected


if __name__ == "__main__":
    sys.exit(main())
