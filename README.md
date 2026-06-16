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
| Static recon→scan→exploit pipelines | **Dynamic recruit-on-discovery** — recon classifies the surface and the Commander recruits the *matching* specialist live: a SQLi surface pulls in the SQLi Hunter, a reflected-input surface the XSS Hunter, a login surface the Auth Breaker |

All offensive activity targets **deliberately-vulnerable, authorized lab targets only** (OWASP Juice Shop). Scope enforcement is a hard, built-in gate — not an afterthought.

---

## Architecture

```
                  BAND CASE ROOM  (every agent holds a persistent WebSocket; the human sees all)
  TIER 0  Human Operator — approves exploitation; holds the kill-switch; reads the live audit stream
  TIER 1  BRAIN AGENTS        Commander · ScopeWarden · Auditor
  TIER 2  SPECIALISTS         Recon Scout · SQLi Hunter · XSS Hunter · Auth Breaker · Reporter
                              (recruited into the room per discovery)
  TIER 3  WORKER TOOL-JOBS    http_probe · crawl · sqlmap · ffuf  (semaphore-bounded fan-out)
```

Band's `@mention` routing means a 30-agent room never floods every agent — each wakes only when called — so the tiered swarm *fits* Band rather than fighting it. Three offensive specialists make recruitment a *real* matching decision: a SQL-injection surface recruits `@leash-sqli-hunter`, a reflected-input surface `@leash-xss-hunter`, and a login surface `@leash-auth-breaker`.

---

## The governance core

The differentiator is implemented first and runs entirely offline (no Band, no API keys):

- [`governance/audit_ledger.py`](governance/audit_ledger.py) — Ed25519-signed, SHA-256 hash-chained, append-only ledger. The signed bytes use a **length-prefixed (injective) encoding** — `SHA256(seq_be64 ‖ len‖kind ‖ hash_prev ‖ len‖payload ‖ len‖sig)` — so no two distinct events can share an encoding and any post-hoc edit breaks verification.
- [`governance/scope_guard.py`](governance/scope_guard.py) — fail-closed allowlist; off-target calls never execute. Path-boundary aware and `..`-normalized, so a `/rest/products` cap can't be escaped by `/rest/products-evil` or `/rest/products/../admin`.
- [`governance/capability.py`](governance/capability.py) — restricted child capabilities (parent ∩ restriction; empty → deny-all).
- [`governance/bundle.py`](governance/bundle.py) — seals the verified ledger + public key into a portable, third-party-verifiable bundle (cross-checks the manifest's tail hash + event count against the re-derived chain).

Quick proof that tampering is detectable:

```bash
uv run pytest tests/test_audit_ledger.py -v
```

---

## Live Control Center

Leash ships a zero-dependency **operator Control Center** ([`viewer/`](viewer/)) — a live dashboard served straight from the Python standard library (no framework, nothing to install):

- **Drive the engagement from the browser.** The human approval gate and the kill-switch are *operated from the UI*. When a specialist requests an exploitation step the gate opens; the operator clicks **Approve** or **Halt**, and the **Kill Switch** is live the whole time.
- **Watch vulnerabilities land.** A severity-ranked findings feed surfaces each confirmed issue as it is discovered — SQL injection, security misconfiguration, sensitive exposure — with OWASP class, endpoint, and evidence, derived live from the audit stream.
- **See the swarm.** A roster shows all eight agents + the operator with live status (idle / engaged / active / awaiting approval / halted).
- **Verify as it streams.** The chain-tail hash and a VERIFIED / TAMPERED badge are re-derived on every append by the same authority as the offline verifier; click any event to inspect its payload, `hash_prev`, and signature.

Crucially, **the operator's own clicks are governed.** The viewer never writes to the ledger — a second writer would break the single-writer hash chain. Instead a click drops a decision file that the engagement (the sole ledger writer) picks up and records as a signed `approval` / `kill_switch` event. So *who approved what* is itself bound into the tamper-evident chain.

It needs no API key — the same control channel that serves the live Band swarm also drives a paced, real-target demo:

```bash
# terminal 1 — the operable Control Center
python -m viewer.viewer --engagement control-demo
# terminal 2 — the paced engagement (real recon + a live, web-driven approval gate)
python scripts/control_demo.py
# then open http://localhost:8089/?engagement=control-demo and hit APPROVE / HALT
```

**Prove the trail cannot be rewritten.** Fork a sealed engagement, alter a single already-signed event, and watch it get caught — the Ed25519 signature no longer matches the mutated payload, so the chain names the exact event and the viewer renders it red:

```bash
python scripts/tamper_demo.py                       # flips one signed event → "TAMPERED — bad signature at seq N"
python -m viewer.viewer --engagement tamper-demo    # the viewer flips VERIFIED → TAMPERED and lights that event red
```

Detection needs only the public key shipped in the bundle — never the private key. That is the whole trust thesis, made visible.

**What this does and does not guarantee (the trust boundary).** The signing key is generated per engagement and written `0600` next to the ledger, so the guarantee is *external, post-hoc tamper-evidence*: anyone holding only the public key can prove that no event was added, removed, or reordered after the fact. It is **not** a defence against a compromised engagement host — whoever can write the ledger directory also holds that engagement's private key and could re-sign a rewritten chain. Hardening that (an HSM, a remote co-signing/notary service, or transparency-log anchoring so the tail hash is witnessed off-host) is the natural next step; the verifier and bundle format already take the public key as input, so none of the verification path changes. Likewise the operator approval recorded into the chain proves *that* an approval was made, not the human identity behind it — the Control Center authenticates by localhost reachability and records a fixed `operator` label, which is appropriate for the single-operator lab demo, not a multi-tenant deployment.

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

The "1000-agent" headline refers to the worker-job fan-out layer — demonstrated with a real benchmark and a connection harness in [`scale_test/`](scale_test/), stated honestly and never faked. Measured this build:

- `worker_fanout_bench --workers 1000 --cap 16` → **1000/1000 jobs** complete, **peak concurrency 16** (cap never exceeded), ~1,305 jobs/s.
- `worker_fanout_bench --workers 200 --target http://localhost:3000` → **200/200 real scope-guarded probes** against the live target, peak 16.
- `connect_harness` → **6/6 live Band WebSockets** held from one host (the prior six-agent roster; the harness reads the roster from `swarm/seed.py`, so it covers the two new specialists once registered).

These worker jobs are coroutines, not 1000 live WebSocket agents — the worker layer scales toward 1000 concurrent **tasks** by distributing across machines, while full 1000-*agent* WS scale needs Band's enterprise tier, with no change to the architecture. [`scale_test/README.md`](scale_test/README.md) spells out exactly what each number proves and does not prove.

---

## Status

Day-3 build. **Verified end-to-end against live OWASP Juice Shop:**

- Governance layer complete — audit ledger (Ed25519 hash-chain with a **length-prefixed, injective signing encoding**), scope guard, capability ACLs, sealed bundle + offline verify CLI, **enforced kill-switch**, and a **code-enforced human approval gate** (offensive tools refuse to exploit until the operator approves at the Control Center — enforced in code, not a prompt convention). **80/80 tests green** (incl. tamper-detection, path-boundary + `..`-traversal + **percent-encoded** (`%2e%2e` / `%2f`) scope bypasses, the cap-never-exceeded scale invariant, fail-closed scoping, kill-switch refusal, the approval-gate fail-closed / timeout paths, and each offensive specialist's confirm / honest-negative / out-of-scope / halted / gate-refusal paths). CI runs `ruff` + the full suite on every push ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)).
- The brain + specialist roster **registers and connects concurrently** — verified **6/6** on the original six-agent roster (`swarm/launcher.py --boot-check`, `scale_test/connect_harness.py`), each wired with role prompts + custom tools. Two newly-added specialists — **XSS Hunter** and **Auth Breaker** — bring the live roster to **eight**: both are fully wired (`swarm/seed.py`, `agent_config.example.yaml`) and unit-tested, with their live boot-check pending their own Band registrations — the only new step is registering the two extra agents at app.band.ai.
- **Band message-delivery confirmed end-to-end:** a kickoff `@mention` posted by one agent was queued by Band and delivered to exactly the right agent (the Commander) on connect, which woke and attempted to reason — the *only* thing standing between here and a live run is `ANTHROPIC_API_KEY`.
- The full **governed pipeline runs deterministically** ([`scripts/offline_demo.py`](scripts/offline_demo.py)) and confirms **three real vulnerability classes** on the live target: recon maps the surface → **security misconfiguration** (missing CSP/HSTS, A05) and **sensitive exposure** (open `/ftp`, version disclosure, A01/A05) flagged → ScopeWarden issues a `/rest/products`-scoped capability → the SQLi hunter reaching for `/ftp` is **blocked by the scope guard** (fail-closed, demonstrated in-script) → operator approval → SQLi **confirmed** (`q=apple'` → HTTP 500) → Auditor **seals a tamper-evident bundle** (7 events, 5 findings) that verifies offline.
- **Three offensive specialists make recruit-on-discovery real** — beyond the SQLi Hunter, the **XSS Hunter** ([`tools/xss_tools.py`](tools/xss_tools.py)) confirms reflected XSS (a uniquely-marked `<svg/onload>` reflected *unescaped* in an HTML response; escaped or non-HTML → honest not-confirmed), and the **Auth Breaker** ([`tools/auth_tools.py`](tools/auth_tools.py)) confirms an OWASP-A07 authentication bypass on the login endpoint by a *differential* check (a SQLi payload that yields a session token where the baseline credential is rejected; otherwise not-confirmed). All three are governed identically — refused when halted, blocked behind the code-enforced approval gate, bounded by the scope guard — and each ships unit tests for every path (confirm / honest-negative / out-of-scope / halted / gate-refusal). With three distinct classes the Commander's "recruit the *matching* specialist" is a genuine decision, not a fixed pipeline. Approval granularity is a deliberate choice — **per-endpoint, persisting for the engagement** (the operator authorizes exploiting an endpoint; the specialist may then work it without re-prompting on each payload), documented in [`swarm/engagement.py`](swarm/engagement.py).
- **Scale layer measured** ([`scale_test/`](scale_test/)): 1000-job fan-out holds the concurrency cap (peak 16/16), 200 real scope-guarded probes against the live target, 6/6 live Band WebSockets held (the prior six-agent roster; the harness reads the roster from `swarm/seed.py`, so it scales to the two new specialists once registered) — every number stated with what it does and does not prove.
- The Band **case-room seeder** ([`swarm/seed.py`](swarm/seed.py)) creates the room and adds the full roster in one command (verified live: 6/6 land on the prior six-agent roster, Commander as owner; the seeder now lists the two new specialists too, pending their registration).
- **Kill-switch is real, not a prompt** — `Engagement.halt()` makes every offensive tool refuse in-process and audits the refusal; the Commander's `issue_kill_switch` tool engages it; [`swarm/kill_switch.py`](swarm/kill_switch.py) ejects the swarm from the room Band-side (verified live: removed 5 specialists, kept the Commander).
- The **Reporter** emits a real deliverable ([report.md](agents/agent_tools.py)) — executive summary, severity rollup, findings table, and an audit attestation block (event count, chain tail, Ed25519 public key, offline verify command).

Reproduction — with Juice Shop on `localhost:3000`:

```bash
python scripts/offline_demo.py
python -m governance.verify engagements/offline-demo/offline-demo_bundle.tar.gz
```

The remaining piece is the live LLM-driven swarm narrating this flow through a Band room (`python -m swarm.launcher`), which needs `ANTHROPIC_API_KEY` in `.env`. The day-by-day to submission (Jun 19) lives in [`docs/BUILD_PLAN.md`](docs/BUILD_PLAN.md).

## License

MIT — see [LICENSE](LICENSE).
