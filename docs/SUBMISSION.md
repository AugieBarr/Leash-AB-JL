# Leash — lablab submission packet

Copy-paste-ready fields for the Band of Agents submission form. Deadline
**2026-06-19 11:00 AM ET**.

---

## Basic information

**Project Title**

```
Leash — Governed Pentest Agent Swarm on Band
```

**Short Description** (≤150 chars)

```
A cross-framework agent swarm that hunts web vulns through a Band room — with scope enforcement, a human approval gate, and a tamper-evident audit chain.
```

**Long Description**

```
Autonomous pentest agents are already here. The field's own practitioners call it a "chaos phase" — agents exceeding scope, dropping tables, leaving no audit trail. Leash is the governed opposite: a swarm of specialized agents that coordinates through a Band room to find and exploit web vulnerabilities safely, with cryptographic guarantees an enterprise can actually trust.

The swarm is tiered. Three "brain" agents — Commander, ScopeWarden, and Auditor — are seeded into the Band room at engagement start via the Band REST API. Specialist agents (Recon Scout, SQLi Hunter, XSS Hunter, Auth Breaker, Prompt-Injection Tester, Data Exposure Sentinel, Reporter) start OUTSIDE the room and are recruited live by the Commander using add_agent_chat_participant the moment recon surfaces the attack class that calls for them. Band membership is operational permission: if you are not in the room, you cannot be @mentioned, and if you cannot be @mentioned, you cannot act.

All inter-agent coordination flows through Band. The Commander @mentions the ScopeWarden to issue each specialist a cryptographic capability (a host/port/path intersection) before it can probe anything; @mentions the Auditor to open the hash-chained ledger and seal the final bundle; and @mentions specialists to hand off work. Nothing fires by side-channel — every handoff is a Band message during the workflow, not before or after it.

Cross-framework by construction: the swarm is not all Python. Aegis is a second-framework agent written in Elixir/OTP that joins the same Band room and shares NO code with the Python SDK (zero hex dependencies — OTP built-ins only). When the ScopeWarden narrows a capability, Aegis independently re-derives that same scope intersection in Elixir and posts its verdict into the room as a governance event — agreement is proven by an identical SHA-256; a mismatch escalates as a halt signal. Two languages, two runtimes, one coordination layer.

Before any destructive tool executes, the specialist posts an in-room request to the human operator and its tool literally blocks — awaiting the operator's APPROVE click in the Control Center. That approval is written as a signed event into the Ed25519 hash-chained ledger. When the engagement closes, the Auditor seals the bundle and posts the chain-tail hash into the Band room. The sealed bundle verifies offline with only the Ed25519 public key (`python -m governance.verify <bundle>` → "Chain OK"); change a single byte and the badge flips TAMPERED and names the bad event.

This makes Leash the first pentest swarm an enterprise can run under compliance: zero out-of-scope risk (fail-closed scope guard enforced in code), full human oversight (the gate blocks in code, not on LLM trust), an auditable kill-switch that ejects all participants from the Band room, and an independently-verifiable audit bundle that holds up in SOC 2, PCI-DSS, and HIPAA reviews. Extending the swarm is leash-by-construction: a scaffolder generates new governed specialists from a one-line spec, with the scope/gate/audit anchors baked in as a fixed template.
```

**Technology & Category Tags**

```
Band, multi-agent, cross-framework, Python, Elixir, cybersecurity, offensive-security, penetration-testing, governance, compliance, audit, human-in-the-loop, kill-switch, Ed25519, OWASP, Claude
```

---

## Cover Image & Presentation

| Field | Source |
|---|---|
| **Cover Image** | `docs/img/control-center.png` (add a title overlay) — the live Control Center with the ten-agent roster, findings feed, and Governance Holds panel |
| **Video Presentation** | Record from `docs/RUNSHEET.md` (≤3:00). The cross-framework Aegis beat lands at the ScopeWarden capability step |
| **Slide Presentation** | `docs/slides.md` (Marp deck — export to PDF/HTML) |

---

## App Hosting & Code Repository

| Field | Value |
|---|---|
| **Public GitHub Repository** | https://github.com/AugieBarr/Leash-AB-JL  *(flip to public before submitting)* |
| **Demo Application Platform** | Hosted demo video (Loom/YouTube) — the demo surface |
| **Application URL** | The repo + the hosted video link |

---

## Judging-criteria crosswalk (what to foreground)

| Criterion | Our strongest evidence |
|---|---|
| **Application of Technology** | Band is the agent event loop + dispatch (@mention) + live recruit (`add_agent_chat_participant`) — not a wrapper. A second framework (Elixir Aegis) coordinates in the same room. |
| **Presentation** | The demo shows the @mention handoff chain + recruit-on-discovery + the human gate + tamper detection — Band visible *throughout*, not just at the ends. |
| **Business Value** | Governance is the #1 enterprise blocker to autonomous offense: scope, oversight, kill-switch, and a regulator-grade audit bundle. |
| **Originality** | Recruit-on-discovery (agents join mid-engagement), leash-by-construction scaffolding, and a genuine cross-framework governance cross-check. |

## Deliverable status (owners)

- [x] Title / Short / Long / Tags — above
- [ ] Cover image (title overlay on control-center.png) — **either**
- [ ] Video (≤3:00, RUNSHEET ready) — **Augie/Josh**
- [ ] Slide deck (`docs/slides.md` → export) — **either**
- [ ] Repo public — **Augie**
- [ ] Hosted video link → Demo Platform / Application URL — **Josh**
- [ ] (optional, strengthens demo) Register `leash-aegis` on Band so Aegis posts its attestation into the live room — **Josh**
```
