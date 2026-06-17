# Leash — Threat Model & Trust Boundaries

Leash is a *governed* offensive-security swarm. This document states exactly what the
governance layer enforces, what it assumes, and what happens at each trust boundary — so
the guarantees can be checked against the code rather than taken on faith. Every claim
cites the file that implements it.

## Deployment model (v1)

The swarm runs as **one process, one asyncio event loop, on one host.** All ten agents'
tool handlers close over a single shared `Engagement` object — one tamper-evident ledger,
one capability registry, one findings list, one `halted` flag
([`swarm/engagement.py`](swarm/engagement.py)). Agents coordinate *through Band* (a shared
room, `@mention` routing, live recruitment); the `Engagement` is the governance substrate
beneath that coordination.

This colocation is a deliberate v1 choice, not an oversight: a single shared object in a
single event loop gives the **strongest possible kill-switch guarantee** — no IPC, no
network, no race between "halt" and the next tool call. The cost is that enforcement is
process-local; see *Cross-process escape* below.

## What is enforced in code (not by prompting the LLM)

These are properties of the code path, so a non-compliant or jailbroken LLM cannot bypass
them:

| Control | Mechanism | Where |
|---|---|---|
| **Kill-switch** | `halt()` sets a flag; every offensive tool calls `refuse_if_halted()` first and the refusal is itself audited | [`swarm/engagement.py`](swarm/engagement.py) (`halt`, `refuse_if_halted`) |
| **Scope leash** | `scope_guard()` raises `ScopeViolationError` *before* any network call; empty/unparseable host fails closed; `..` is normalized away before the prefix check so `/rest/products/../admin` can't escape a `/rest/products` cap | [`governance/scope_guard.py`](governance/scope_guard.py) |
| **Capability ACL** | each child cap is parent ∩ restriction; an empty field denies all | [`governance/capability.py`](governance/capability.py) |
| **Human approval gate** | every offensive tool (`manual_sqli_probe`, `run_sqlmap`, `manual_xss_probe`, `manual_auth_bypass_probe`) checks the scope guard *then* blocks in `enforce_gate()` until the operator approves — enforced inside the tool, not by prompt; the approval is logged to the chain | [`tools/sqli_tools.py`](tools/sqli_tools.py), [`tools/xss_tools.py`](tools/xss_tools.py), [`tools/auth_tools.py`](tools/auth_tools.py), [`swarm/control_channel.py`](swarm/control_channel.py) |
| **Tamper-evident audit** | every governed action is Ed25519-signed and SHA-256 hash-chained under an `asyncio.Lock`; any post-hoc edit breaks verification | [`governance/audit_ledger.py`](governance/audit_ledger.py) |
| **Single-writer integrity** | the browser Control Center never writes the ledger; it drops a decision file the engagement (sole writer) records — atomic `os.replace` so the poller never reads a half-write | [`swarm/control_channel.py`](swarm/control_channel.py) |

## What Band carries — and what happens if Band drops

Band is the **coordination plane**: the room, live recruitment, `@mention` handoffs, and
code-dispatched governance broadcasts. The governance **substrate** (chain, scope,
capabilities, halt) is in-process and does not depend on Band.

If Band went down mid-engagement:

- **Keeps working:** the audit chain keeps writing (local NDJSON), the scope guard keeps
  blocking out-of-scope calls, the capability ACLs keep narrowing, and the kill-switch
  keeps refusing every offensive tool. None of these touch Band.
- **Stops working:** new specialist *recruitment* (`recruitspecialist` calls Band's REST
  `add_agent_chat_participant`, [`agents/agent_tools.py`](agents/agent_tools.py)),
  `@mention` handoffs (LLM-driven via Band's `send_message` platform tool), and the
  **code-dispatched governance broadcasts** — e.g. the Auditor posting the sealed
  chain-tail hash into the room (`post_governance_signal`,
  [`swarm/_band_client.py`](swarm/_band_client.py), called from `sealbundle`).

That last point is the honest answer to "is Band load-bearing?": the seal announcement is
a deterministic Band event, so it is demonstrably lost if Band drops — Band is the
coordination and broadcast channel, not a decorative chat log. But it is **not** the
governance enforcement engine, and we don't claim it is.

## Cross-process escape (named v1 boundary)

Because enforcement is process-local, a specialist running in a **separate process or
container** would not share the `halted` flag, the `approvals` set, or the capability
registry. Within one process the flag is an unforgeable Python bool checked before every
tool call; across processes it is not visible. This is the explicit v1 trust boundary —
stated, not hidden.

**v2 upgrade path** (architecture unchanged): a governance sidecar exposing
halt/scope/approval over a signed IPC channel, or Band `send_event` as the cross-process
halt broadcast, with capabilities issued as signed (JWT-style) tokens each specialist must
present. The capability model ([`governance/capability.py`](governance/capability.py)) is
already token-shaped for this.

## Boundaries surfaced by adversarial review (2026-06-16)

A multi-agent security audit (38 agents; every critical/high finding re-verified against
the code) surfaced the boundaries below. None is remotely exploitable in the v1 model — the
swarm and its Control Center run on **one operator's host**, bound to `127.0.0.1` — but each
is named here with its hardening path, because a governance product should state its own
edges rather than wait for a judge to find them.

| Boundary | Why it is bounded in v1 | Hardening path |
|---|---|---|
| **Control Center `/control` has no token auth** — any process on the operator's host can POST `approve`/`halt` ([`viewer/viewer.py`](viewer/viewer.py)); the Origin-less allowance is deliberate so the local recording scripts can drive the gate. | The server binds `127.0.0.1`; a local process with that access already holds the private key and the decision files, so forging an approval is not an escalation. | A shared `X-Leash-Token` (written `0600` beside the ledger on viewer start), required on every `/control` POST — closing it for multi-user / remote operation. |
| **The viewer loads the private key to derive the public key** ([`viewer/viewer.py`](viewer/viewer.py) `_pubkey_for`), though it only ever verifies, never signs. | The private key already sits on the operator's host beside the ledger, so the local viewer reading it is not a new exposure. | A sibling `engagement_ed25519.pub` for the viewer to read instead, so the operator console provably cannot sign. |
| **Approval persists per-endpoint, not per-`(tool, endpoint)`** ([`swarm/engagement.py`](swarm/engagement.py) `is_approved`): one approval for a path lets a specialist run further payloads/tools on it without re-prompting. | A deliberate scope choice — the operator authorizes *exploiting this endpoint*; the normalized-path key cannot be widened by query/`*`/`..` decoration. | Keying `approvals` by `(tool, endpoint)`, or a time-box — the one-line change is named in the code comment. |
| **The kill-switch stops new subprocesses, not an in-flight one** ([`tools/_subprocess.py`](tools/_subprocess.py) `scoped_run`): a halt refuses to *spawn*; an already-running `sqlmap` finishes or hits its per-tool timeout (≤120 s). | Every *new* offensive tool is refused instantly in-process; the only thing that outlives a halt is a subprocess already executing, which is time-boxed. | Racing `proc.communicate()` against an `eng.halted` poll, killing the process on halt. |
| **One open approval gate at a time** ([`swarm/control_channel.py`](swarm/control_channel.py)): a single `decision.json` per engagement assumes one operator and one specialist exploiting at a time (the role briefs enforce this). | An `approve` only satisfies its own `gate_id` and a `halt` is global, so a stale decision cannot cross-satisfy a later gate. | Per-gate `decision-<gate_id>.json` files for truly simultaneous specialist gates. |

**Closed during this review:** resuming a ledger to append now verifies the whole chain
first (`verify_on_resume`, [`governance/audit_ledger.py`](governance/audit_ledger.py)), so a
ledger tampered between runs is refused rather than silently extended; and the Commander's
`recruitspecialist` now rejects any `agent_label` outside the known roster, so a
prompt-injected Commander cannot pull an arbitrary agent into the room
([`agents/agent_tools.py`](agents/agent_tools.py)).

## The three questions, answered

**"If Band went down, what governance stops working?"**
None of it. The chain, halt flag, capability ACLs, and scope guard are all in-process and
Band-independent. What stops is *coordination* — recruitment, `@mention` handoffs, and the
seal broadcast — which is exactly why Band is the coordination plane, not the governance
plane.

**"What stops a compromised specialist in a separate container from ignoring the halt
flag?"**
In v1, the process boundary. Within one event loop the halt is an unforgeable shared bool
checked before every offensive tool ([`swarm/engagement.py`](swarm/engagement.py),
`refuse_if_halted`). A separate container can't see it — named here as the v1 boundary,
with the IPC / `send_event` upgrade path above.

**"Is this just sqlmap with a logger?"**
No. sqlmap has no capability ACL (Leash blocks out-of-scope targets *before* the network
call, [`governance/scope_guard.py`](governance/scope_guard.py)), no human-approval gate
enforced in code, and no tamper-evident, offline-verifiable record where the *approval
itself* is sealed into the same Ed25519 chain as the exploit. The SQLi probe is one line;
the governed swarm around it is the product.
