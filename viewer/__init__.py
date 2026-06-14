"""Live audit-stream viewer for a Leash engagement.

A zero-dependency, read-only web view that tails an engagement's hash-chained
``audit.ndjson`` over Server-Sent Events and shows the governance story as it
happens: each event streaming in, the running chain-tail hash, and a live
VERIFIED / TAMPERED badge re-checked on every append.
"""
