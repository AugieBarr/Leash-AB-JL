# Live audit-stream viewer

A zero-dependency web view that makes the governance story **visible**: it tails
an engagement's hash-chained `audit.ndjson` over Server-Sent Events and shows
every event as it lands, the running chain-tail, and a **VERIFIED / TAMPERED**
badge that is re-derived on every append.

It is the visible twin of `python -m governance.verify` — the same Ed25519
chain-verification, streamed instead of printed once.

```bash
python -m viewer.viewer                      # http://localhost:8089
python -m viewer.viewer --engagement offline-demo
python -m viewer.viewer --port 9000
```

The engagement picker lists every `engagements/<id>/` that has an `audit.ndjson`.
The public key is read from that engagement's own `engagement_ed25519.key`
(present on the operator's machine for a live run), exactly as the offline
verifier does it.

## Showing tamper-detection in the demo

The badge flips to **✗ tampered** the instant the ledger stops verifying. To show
it live, copy a finished engagement and rewrite one event's history:

```bash
cp -r engagements/offline-demo engagements/tamper-demo
# edit any payload in engagements/tamper-demo/audit.ndjson — e.g. approved -> denied
python -m viewer.viewer --engagement tamper-demo
# badge: ✗ tampered — "bad signature at seq N"
```

Verified against the real `offline-demo` ledger: an untouched chain reads
*"Chain OK — N events, no tampering detected"*; flipping any event's payload (e.g.
an approval's `approved` → `denied`) flips the badge to *"bad signature at seq K"*
for the edited event. (Counts vary per demo run.)

> Read-only. The viewer never writes to the ledger — it only verifies and
> displays. Built on the standard-library HTTP server so the demo needs nothing
> installed beyond the project's existing dependencies.
