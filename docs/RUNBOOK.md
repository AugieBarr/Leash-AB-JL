# Leash — Runbook

Three levels of demonstration, from zero-setup to the full live swarm. Each is one
or two commands. Targets in the `Makefile`; this doc is the operator narrative.

> Authorized-scope reminder: all offensive activity targets **OWASP Juice Shop**
> on `localhost:3000` — a deliberately-vulnerable lab app — only.

---

## Prerequisites

| For… | You need |
|---|---|
| The target-free proof (Part A) | [`uv`](https://docs.astral.sh/uv/) only |
| The governed demo (Part B) | `uv` + Docker (for Juice Shop) |
| The live Band swarm (Part C) | `uv` + Docker + a **Band account** (app.band.ai) + an **`ANTHROPIC_API_KEY`** |

```bash
make install      # uv sync --extra dev
```

---

## Part A — Target-free proof (no Docker, no Band, no API key)

The governance, crypto, scope-guard, gate/kill-switch, and scale claims need **no
live target**. A reviewer can verify all of them in a bare checkout:

```bash
make proof        # ruff + full test suite + the 1000-job concurrency-cap benchmark
```

Expect: `All checks passed`, `97 passed`, and `1000/1000 jobs, peak concurrency 16 (cap held)`.

To watch tamper-evidence specifically:

```bash
make test         # incl. byte-level tamper, truncation, traversal, gate, kill-switch tests
```

---

## Part B — Deterministic governed demo (Docker; no Band, no LLM)

The full governed pipeline against the real target, with **no API key** — proves
the governance + tooling work end-to-end and produces a verifiable sealed bundle:

```bash
make demo         # juice-shop up → offline_demo.py → verify the sealed bundle
```

This runs: recon maps the surface → security-misconfiguration + sensitive-exposure
flagged → ScopeWarden scopes the SQLi hunter to `/rest/products` → the hunter
reaching for `/ftp` is **blocked by the scope guard** → operator approval (pre-recorded)
→ SQLi **confirmed** → Auditor **seals a tamper-evident bundle** that verifies offline.

The live **Control Center** + the web-driven approval gate, still without an API key:

```bash
# terminal 1
make viewer                    # http://localhost:8089
# terminal 2
make control-demo              # paced real recon + a live, web-driven gate
# then open http://localhost:8089/?engagement=control-demo and hit APPROVE / HALT
```

Prove the trail cannot be rewritten:

```bash
make tamper-demo               # flips one signed event → "TAMPERED — bad signature at seq N"
make viewer                    # open ?engagement=tamper-demo → VERIFIED flips to TAMPERED
```

---

## Part C — Live LLM-driven Band swarm

This is the headline: eight agents coordinating in a real Band room, the Commander
recruiting the *matching* specialist on discovery, the human driving the gate from
the Control Center.

### C.1 Register the 8 agents (once)

At **app.band.ai**, under **one** Band account (so they are siblings and can
recruit each other), create eight agents (New Agent → Remote/External) and copy
each `agent_id` + `api_key`:

```
leash-commander   leash-scope-warden  leash-auditor    leash-recon-scout
leash-sqli-hunter leash-xss-hunter    leash-auth-breaker  leash-reporter
```

### C.2 Fill the secrets (gitignored — never committed)

```bash
cp env.example .env                          # then set ANTHROPIC_API_KEY
cp agent_config.example.yaml agent_config.yaml   # then fill the 8 agent_id + api_key pairs
```

### C.3 Connectivity check first (no Anthropic key needed)

```bash
make boot-check                              # connects all 8, expect "8/8 agents online"
```

If this prints `8/8`, Band auth + WebSockets are good. (This is the cheapest signal
that the credentials work — run it before anything else.)

### C.4 Run the swarm

```bash
# terminal 1 — the Control Center
make viewer                                  # http://localhost:8089/?engagement=demo-01
# terminal 2 — the lab target + the swarm
make live                                    # juice-shop up + python -m swarm.launcher
```

Seed the room and kick it off. For a human-in-the-loop demo, prefer creating the
room in the Band UI (add the 8 agents) and typing the kickoff so a real human is
present for the gate; or headless:

```bash
make seed                                    # creates the room, adds the roster, posts the kickoff
```

Kickoff message (if typing it yourself):

```
@leash-commander Begin the authorized engagement against localhost:3000 (OWASP Juice Shop).
```

### C.5 Drive it

In the Control Center: watch recon land → the Commander recruit the matching
specialist → when a specialist requests exploitation the **gate opens** → click
**APPROVE** (or **HALT** — the kill-switch is live the whole time). Then have the
Auditor seal the bundle and verify it:

```bash
make verify                                  # or: python -m governance.verify engagements/demo-01/demo-01_bundle.tar.gz
```

---

## What to capture for the submission video (~60s)

1. `make proof` scrolling green (governance + scale, no target). *(2s b-roll)*
2. The Band room: a kickoff `@mention` → the Commander recruiting `@leash-sqli-hunter`
   (or xss/auth) for the *matching* discovery.
3. The Control Center: a specialist's gate request → the human clicking **APPROVE**.
4. A vulnerability landing in the live feed + the VERIFIED badge advancing.
5. `make verify` printing `Chain OK — N events, no tampering detected` from the
   public key alone.

That clip converts "impressive governance core with a pending demo" into "working
governed swarm."

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `make demo` → "Juice Shop not reachable" | Docker isn't running, or the image is still pulling. `docker compose up -d juice-shop`, wait ~20s, retry. |
| `make boot-check` → fewer than 8/8 | An `agent_config.yaml` entry is wrong, or the agent isn't registered under the same Band account. The failing label is printed. |
| Launcher exits: "ANTHROPIC_API_KEY is not set" | Set it in `.env` (the live LLM run needs it; `boot-check` does not). |
| Viewer: "Could not bind …:8089" | Another viewer is running — stop it or `python -m viewer.viewer --port 9000`. |
| Agents connect but nothing happens | Make sure a kickoff `@mention` to `@leash-commander` was actually posted (`make seed`, or type it in the Band UI). |
