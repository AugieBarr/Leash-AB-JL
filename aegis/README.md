# Aegis — the cross-framework scope attestor (Elixir/OTP)

Aegis is a second-framework agent for [Leash](../README.md). It is written in
**Elixir/OTP** and shares **no code** with the Python swarm — the only thing the
two runtimes have in common is the **Band room**. That is the cross-framework
claim made literal: two languages, two runtimes, one coordination layer.

## What it does

When the Python **ScopeWarden** narrows the engagement capability for a
specialist (`parent ∩ restriction`), Aegis **independently recomputes that
intersection in Elixir** and posts the verdict into the same Band room as a
governance event:

- **MATCH / attested** → a `tool_result` event: the second framework agrees the
  grant is correct (`sha256` fingerprint included).
- **MISMATCH / empty-scope deny** → an `error` event recommending HALT: the two
  frameworks *disagree* on the grant, which is exactly the condition you want a
  cross-check to surface.

The scope algebra (`Aegis.Scope`) is an independent re-derivation of the same
host/port/path rules the Python `governance/capability.py` implements — which is
*itself* a clean-room port of `Hermes.Themis` (Elixir). Aegis brings the Elixir
original back into the room as a live attestor. The two implementations agree by
producing the **same canonical scope and the same SHA-256**; if they ever diverge,
the attestation goes red.

## Why this is real cross-framework coordination

- **Separate runtime:** Elixir/OTP, not Python. Built with **zero hex
  dependencies** — only OTP built-ins (`:httpc`, `:ssl`, `:json`, `:crypto`) — so
  there is no shared SDK with the Python side.
- **Through Band:** Aegis authenticates with its own Band agent key and posts a
  structured event into the shared room over the Band REST API
  (`POST /api/v1/agent/chats/{id}/events`). The attestation is a room event the
  human operator and every other agent see — coordination *through* Band, during
  the workflow.
- **A genuine governance function:** independent re-derivation of a security
  grant, not a notification. Disagreement escalates as a halt signal.

## Run it

```bash
mix deps.get        # none — there are no dependencies
mix test            # 14 tests: scope algebra matches the Python evaluator + attestation logic
mix escript.build   # builds the ./aegis binary
```

**Offline (no key, no network)** — prove the Elixir re-derivation:

```bash
./aegis attest --host localhost --port 3000 --parent-paths / \
               --restrict-paths /rest/products --dry-run
# 🛡️ AEGIS (Elixir/OTP) attests the ScopeWarden grant — scope hosts=localhost;ports=3000;paths=/rest/products …

./aegis attest --restrict-paths /rest/products \
               --expect-hash <scopewarden-hash> --dry-run     # MATCH / MISMATCH
./aegis attest --restrict-port 9999 --dry-run                 # empty-scope DENY (exit 2)
```

**Live (posts into a Band room)** — Aegis must be a participant in the room:

```bash
export AEGIS_API_KEY=...            # Aegis's Band agent key (never passed on the CLI)
export BAND_REST_URL=https://app.band.ai/
./aegis check                       # read-only: proves this runtime authenticates to Band
./aegis attest --room <chat_id> --restrict-paths /rest/products \
               --expect-hash <scopewarden-hash>
```

## Configuration

| Env var | Purpose | Default |
|---|---|---|
| `AEGIS_API_KEY` | Aegis's Band agent API key (required unless `--dry-run`) | — |
| `BAND_REST_URL` | Band REST base URL | `https://app.band.ai/` |

Credentials are read from the environment only — never the command line, never
logged.

## Layout

```
aegis/
  lib/aegis.ex          # derive the attestation + post it into the room
  lib/aegis/scope.ex    # the host/port/path algebra (mirrors governance/capability.py)
  lib/aegis/band.ex     # zero-dependency Band REST client (:httpc/:ssl/:json)
  lib/aegis/cli.ex      # escript entry: `aegis attest …` / `aegis check`
  test/                 # ExUnit: algebra parity + attestation logic
```
