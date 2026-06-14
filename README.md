# Leash 🐕‍🦺

**A governed offensive agent swarm — built on [Band](https://band.ai).**

Autonomous web-app penetration testing where a tiered swarm of agents coordinates *through a Band room*, recruits specialists as it discovers attack surface, **stops at a human approval gate before it exploits anything**, and emits a **tamper-evident, independently-verifiable audit bundle** when the engagement closes.

> Built for the **Band of Agents Hackathon** (lablab.ai, Jun 2026) by Team Roan — Josh Langsam ([@joshualangsam-a11y](https://github.com/joshualangsam-a11y)) & Augie Barreirinhas ([@AugieBarr](https://github.com/AugieBarr)).

---

## Why Leash

Autonomous pentest is already a crowded field — 39+ open-source agents, XBOW topping HackerOne, HexStrike-AI driving 150+ tools. But the field has a hole everyone names and nobody fills: **governance.** XBOW's own CISO calls it a *"chaos phase… we are not ready,"* with agents *"dropping your tables."* The tools optimize for autonomous execution over audit trails or scope enforcement.

Leash is the **governed** swarm — the anti-HexStrike. Band gives it exactly the controls the field lacks:

| Field's gap | What Leash does on Band |
| --- | --- |
| No scope enforcement | A fail-closed scope guard + a ScopeWarden agent that issues each specialist a restricted capability it cannot exceed |
| No audit trail | Every agent action becomes a Band event, hash-chained into a tamper-evident ledger and sealed into a verifiable bundle |
| "Dropping your tables" | A **human approval gate** before any destructive action, and a Commander kill-switch that ejects the swarm |
| Static recon→scan→exploit pipelines | **Dynamic recruit-on-discovery** — recon finds a SQLi surface and the SQLi specialist joins the room live |

All offensive activity targets **deliberately-vulnerable, authorized lab targets only** (OWASP Juice Shop). Scope enforcement is a hard, built-in gate — not an afterthought.

---

## Architecture

```
                  BAND CASE ROOM  (every agent holds a persistent WebSocket; the human sees all)
  TIER 0  Human Operator — approves exploitation; holds the kill-switch; reads the live audit stream
  TIER 1  BRAIN AGENTS        Commander · ScopeWarden · Auditor
  TIER 2  SPECIALISTS         Recon Scout · SQLi Hunter · [XSS Hunter] · [Auth Breaker] · Reporter
                              (recruited into the room per discovery)
  TIER 3  WORKER TOOL-JOBS    http_probe · crawl · sqlmap · ffuf  (semaphore-bounded fan-out)
```

Band's `@mention` routing means a 30-agent room never floods every agent — each wakes only when called — so the tiered swarm *fits* Band rather than fighting it.

---

## The governance core

The differentiator is implemented first and runs entirely offline (no Band, no API keys):

- [`governance/audit_ledger.py`](governance/audit_ledger.py) — Ed25519-signed, SHA-256 hash-chained, append-only ledger. Chain hash: `SHA256(seq_be64 ‖ kind ‖ hash_prev ‖ payload ‖ sig)`. Any post-hoc edit breaks verification.
- `governance/scope_guard.py` *(in progress)* — fail-closed allowlist; off-target calls never execute.
- `governance/capability.py` *(in progress)* — restricted child capabilities (parent ∩ restriction; empty → deny-all).
- `governance/bundle.py` *(in progress)* — seals the verified ledger + public key into a portable, third-party-verifiable bundle.

Quick proof that tampering is detectable:

```bash
uv run pytest tests/test_audit_ledger.py -v
```

---

## Quickstart

```bash
# 1. Stand up the authorized lab target
docker compose up -d juice-shop      # OWASP Juice Shop on http://localhost:3000

# 2. Python env (uv)
uv sync --extra dev

# 3. Governance tests (offline — no Band, no API key needed)
uv run pytest -v

# 4. Band credentials (per agent, registered once at app.band.ai)
cp env.example .env                  # then fill ANTHROPIC_API_KEY
cp agent_config.example.yaml agent_config.yaml   # then fill agent_id + api_key per agent
```

`.env` and `agent_config.yaml` are gitignored — secrets never get committed.

---

## Scale

The live demo runs ~10–30 **real** Band agents. The "1000-agent" headline refers to the worker-job fan-out layer, demonstrated with a benchmark and a connection harness — stated honestly, never faked. The worker layer scales toward 1000 concurrent tasks by distributing across machines; full 1000-WebSocket-agent scale needs Band's enterprise tier, with no change to the architecture.

---

## Status

Day-3 build, in progress. The audit ledger and tamper test are green; agents, scope guard, capability ACLs, and the bundle sealer are landing next. See the build plan for the day-by-day to submission (Jun 19).

## License

MIT — see [LICENSE](LICENSE).
