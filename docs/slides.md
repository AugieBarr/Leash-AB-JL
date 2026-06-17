---
marp: true
theme: uncover
class: invert
paginate: true
style: |
  :root {
    --accent: #E8735A;
    --ok: #4ADE9E;
  }
  section {
    background: #14110F;
    color: #EDE7E1;
    font-family: 'Geist', 'Inter', system-ui, sans-serif;
    font-size: 28px;
    text-align: left;
    justify-content: flex-start;
    padding: 64px 72px;
  }
  h1, h2 { color: #fff; letter-spacing: -0.02em; }
  h1 { font-size: 56px; }
  strong { color: var(--accent); }
  code { color: var(--accent); background: #221C18; }
  a { color: var(--accent); }
  .ok { color: var(--ok); }
  table { font-size: 24px; }
  blockquote { border-left: 3px solid var(--accent); color: #C9BFB6; }
---

<!-- _class: invert -->
# Leash 🐕‍🦺

### A **governed** pentest agent swarm — coordinated through Band

Scope enforcement · human approval gate · tamper-evident audit · **a second framework in the room**

<br>

Team Roan — Josh Langsam & Augie Barreirinhas · Band of Agents Hackathon

---

## The governance gap

**Autonomous pentest agents are already here** — 39+ OSS agents, XBOW topping HackerOne, HexStrike driving 150+ tools.

> XBOW's own CISO calls it a *"chaos phase… we are not ready"* — agents *"dropping your tables."*

The field optimizes for **autonomous execution** over **scope, audit, and a stop button.**

**That gap is the product.**

---

## Leash: the governed swarm

```
        BAND ROOM   (human operator sees every event, live)
  ┌─────────────────────────────────────────────────────┐
  │  BRAIN     Commander · ScopeWarden · Auditor          │
  │  SPECIALISTS  Recon · SQLi · XSS · Auth · Injection · │
  │               Data-Exposure · Reporter  (recruited)   │
  │  CROSS-FW  Aegis (Elixir/OTP) — scope attestor        │
  └─────────────────────────────────────────────────────┘
```

Band is **where the agents live and coordinate** — not a notification bus.

---

## Band *is* the collaboration layer

| Band primitive | Leash usage |
|---|---|
| Room + participant API | `create_agent_chat` seeds the brain tier |
| **WebSocket event loop** | every agent's `run()` IS the loop — Band wakes them |
| **`@mention` routing** | selective dispatch — a 10-agent room stays coherent |
| **`add_agent_chat_participant`** | **recruit-on-discovery, live, mid-engagement** |

Not before. Not after. **Through Band, during the workflow.**

---

## Recruit-on-discovery

Specialists **don't exist in the room** until they're needed.

1. Brain tier seeded — Commander, ScopeWarden, Auditor.
2. Recon classifies the surface → SQLi candidate found.
3. Commander calls `recruitspecialist` → **SQLi Hunter joins the room live.**
4. A `frozenset` allowlist guards it — a prompt-injected Commander **cannot** pull an arbitrary agent in.

**Runtime topology driven by agent-discovered state** — not a static pipeline.

---

## Cross-framework: a second runtime in the room

**Aegis** is an **Elixir/OTP** agent that joins the same Band room — **zero shared code** with the Python SDK (OTP built-ins only).

- When the ScopeWarden narrows a capability, Aegis **independently re-derives the host/port/path intersection in Elixir.**
- Agreement proven by an **identical SHA-256**; a mismatch posts an **`error` + halt signal** into the room.
- <span class="ok">Live-verified</span>: Elixir → Band auth `HTTP 200`; 14 ExUnit tests.

**Two languages, two runtimes, one coordination layer.**

---

## The leash: scope · gate · kill-switch

- **Scope** — ScopeWarden issues each specialist a cryptographic capability (host/port/path ∩). A fail-closed guard blocks any off-target reach **in code**.
- **Approval gate** — destructive tools **block** on the operator's APPROVE click. Enforced in code, not on LLM trust.
- **Kill-switch** — `halt()` makes every tool refuse in-process; the Commander ejects the swarm from the Band room.

Governance is **Band-SDK-free** — it holds even if Band drops.

---

## Tamper-evident audit chain

Every action → **Ed25519-signed, SHA-256 hash-chained** event, single-writer.

```
seq ‖ kind ‖ hash_prev ‖ payload ‖ sig   (length-prefixed, injective)
```

- Seal → portable bundle, verifiable **offline with only the public key.**
- `python -m governance.verify <bundle>` → <span class="ok">"Chain OK — N events"</span>
- Change one byte → **TAMPERED**, the bad event named.

*Clean-room port of a production Elixir audit system.*

---

## Live demo

1. **Band room** — Commander recruits, ScopeWarden grants, **Aegis (Elixir) attests.**
2. **Scope holds** — SQLi Hunter reaches for `/ftp` → **blocked.**
3. **Human gate** — operator clicks APPROVE → SQLi confirmed → HIGH finding.
4. **Seal → Band** — chain-tail hash posted into the room.
5. **Tamper** — one byte changed → badge flips **TAMPERED.**

---

## Enterprise value

| Field pain | Leash |
|---|---|
| Agents exceed scope | Capability + fail-closed guard |
| No audit trail | Ed25519 hash chain → offline-verifiable bundle |
| *"Dropping your tables"* | Human gate + kill-switch |
| Compliance evidence by hand | The bundle **is** the SOC 2 / PCI / HIPAA artifact |

**The first pentest swarm you can run under compliance.**

---

## Stack

- **Band SDK** (`band-sdk[anthropic,claude_sdk]`) — coordination layer
- **Python 3.11 + asyncio** — swarm runtime
- **Elixir/OTP** — Aegis cross-framework attestor (zero deps)
- **cryptography (Ed25519)** — audit chain
- **OWASP Juice Shop** — authorized lab target
- **110 Python tests + 14 Elixir tests**, CI on every push

---

<!-- _class: invert -->
# Leash

**Governed. Cross-framework. On Band.**

github.com/AugieBarr/Leash-AB-JL

```bash
docker compose up -d juice-shop
python -m swarm.launcher --engagement-id demo --seed --brain-only
```
