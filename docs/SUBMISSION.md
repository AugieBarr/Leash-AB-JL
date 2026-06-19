# Leash — Submission Package & Demo Handoff

Everything for the lablab.ai **Band of Agents** submission in one place. Sections
1–4 are the submission-form copy + slides + video script; **Section 5 is the
"run the demo on your machine" guide for Josh.** Deeper detail lives in
`docs/RUNBOOK.md` (operations) and `docs/DEMO_SCRIPT.md` (full storyboard).

Repo: https://github.com/AugieBarr/Leash-AB-JL · branch `claude/charming-allen-jiphaq`

---

## 1. Submission form copy

**Project title:** Leash

**Tagline:** A governed offensive-security agent swarm on Band — autonomy you can actually run.

**Short description** *(249 chars, ≤255):*
> A governed offensive-security swarm on Band. Eight agents coordinate in a Band room to pen-test a web app — recruiting the matching specialist on discovery, gating exploits behind human approval, and sealing a tamper-evident, verifiable audit trail.

**Long description** *(≥100 words):*
> Autonomous penetration testing is a natural fit for multi-agent systems — map a target, divide the work across specialists, exploit, and report. The blocker for enterprises has never been capability; it's control. Today's offensive agents run without scope, audit, or a human in the loop, so no regulated organization can point them at production.
>
> Leash is a governed offensive-security swarm built on Band. Eight specialized agents — a Commander, a ScopeWarden, an Auditor, a Recon Scout, three offensive specialists (SQL injection, cross-site scripting, authentication bypass), and a Reporter — coordinate through a Band room. **Band is the coordination layer:** it gives each agent identity, presence, and @mention routing, so the Commander recruits the *matching* specialist into the room the moment recon discovers a vulnerability class. Every exploit is gated behind a code-enforced human approval, bounded by a fail-closed scope guard, and recorded into an Ed25519-signed, tamper-evident audit chain anyone can verify from the public key alone. A kill-switch ejects the swarm from the room instantly. **Band makes the swarm possible; Leash makes it safe enough for enterprise security.**

**Technology & category tags:**
`Band` · `Multi-Agent Systems` · `Agent Orchestration` · `AI Agents` · `Anthropic Claude` · `Cybersecurity` · `Offensive Security / Penetration Testing` · `DevSecOps` · `Governance & Compliance` · `Cryptography / Audit` · `Python`
Primary category: **Cybersecurity / Enterprise**.

**Cover image (16:9, PNG/JPG):** a single frame of the **Control Center** mid-engagement
— the 8-agent roster with live statuses, the severity-ranked findings feed, and the
green **VERIFIED** chain badge. Capture recipe: run the demo (Section 5), open
`http://localhost:8089/?engagement=demo-01`, wait until a finding has landed and the
badge reads VERIFIED, screenshot at 1920×1080. (It's the most striking single frame.)

**Application URL:** the Control Center is a zero-dependency web app. Options, easiest first:
- Record-and-host a short interaction, or deploy the read-only viewer (it's stdlib `http.server`) to Replit/Vercel/a small VM.
- If a live URL isn't feasible by the deadline, point to the repo + the `make control-demo` one-command interactive demo.

---

## 2. Slide deck outline (PDF — keep each slide to 2–3 sentences)

1. **Title** — "Leash: A Governed Offensive-Security Agent Swarm on Band." Tagline + team + "Built on Band."
2. **The problem** — Enterprises want agents to find their security holes, but won't run ungoverned offense: no scope, no audit, no human in the loop. ("Chaos phase… dropping your tables.") Capability isn't the blocker — *control* is.
3. **The solution** — Leash: eight specialized agents that pen-test a target *and* stay governed, coordinating through a Band room.
4. **Architecture** *(the Band diagram)* — Commander · ScopeWarden · Auditor · Recon Scout · SQLi / XSS / Auth specialists · Reporter, all in one Band room. Label it: **"Band = the coordination layer."**
5. **How Band coordinates** — @mention routing (each agent wakes only when called), **recruit-on-discovery** (the Commander pulls the matching specialist into the room), the room as shared context, and a Band-side kill-switch that removes participants.
6. **Governance core** — Fail-closed scope guard (capabilities an agent can't exceed), a **code-enforced** human approval gate before any exploit, and an Ed25519-signed, tamper-evident audit bundle verifiable by anyone from the public key alone.
7. **What runs today** — 3 real vuln classes confirmed on OWASP Juice Shop; 8/8 agents hold live Band WebSockets; 1000-job worker tier holds its concurrency cap; 98 tests green; sealed bundle verifies offline.
8. **Business value** — Governed autonomy is the unlock for enterprise security automation. Reduces manual pentest coordination, produces regulator-ready audit trails. Market: the AppSec/pentest-automation space; the *governance gap* is the wedge vs. XBOW / HexStrike (capability-first, control-light). USP = **governance as the product.**
9. **Future** — More specialists, cross-framework agents in one room, HSM/notary for the signing key, Band's enterprise WS tier for larger swarms.
10. **Close** — "Band makes the swarm possible; Leash makes it safe." Repo + demo link.

---

## 3. Demo video — voiceover script (~3:30)

Read this into the mic over the recorded footage. Full storyboard + shot list +
rubric-coverage map are in `docs/DEMO_SCRIPT.md`. Bracketed cues are not spoken.

> **[Hook]** Enterprises want autonomous agents to find their security holes. But nobody will point an AI swarm at production — because today's offensive agents have no governance. No scope. No audit trail. No human in the loop. **Leash fixes that — a governed offensive-security swarm, built on Band.**
>
> **[Architecture slide]** Leash is eight specialized agents that coordinate through a Band room — and **Band is the coordination layer.** It gives every agent an identity, a persistent connection, and @mention routing, so the swarm hands work off without flooding each other. A Commander orchestrates. A ScopeWarden issues each agent a capability it cannot exceed. An Auditor keeps a tamper-evident record. A Recon Scout maps the surface. And three offensive specialists — SQL injection, XSS, and auth bypass — each join only when they're needed.
>
> **[Band room]** Here's a live engagement. Eight agents, each connected to Band, sharing one room. This room *is* the shared context — every hand-off and decision happens here, where the human can see it.
>
> **[Kickoff + delegation]** The operator starts it with one @mention to the Commander, which delegates — ScopeWarden to set scope, Auditor to open the chain, Recon to map the target. Every hand-off is an @mention; every agent wakes only when called.
>
> **[Recruit-on-discovery]** Recon flags a SQL-injection surface. That's the trigger. The Commander recruits the *matching* specialist into the room, live. This is what a script can't do: **the swarm assembles itself around what it discovers.**
>
> **[Gate]** But before it exploits anything, the SQLi Hunter posts its intent and escalates to the human. The operator approves from the Control Center — and that approval is **signed into the shared audit chain**. The gate is enforced in code, not a prompt.
>
> **[Confirm + kill-switch]** The exploit runs, the vulnerability is confirmed. And if anything looks wrong, the Commander's kill-switch ejects every specialist from the Band room instantly.
>
> **[Verify]** The Auditor seals a bundle anyone can verify — from the public key alone. Chain OK. Nothing added, altered, or removed.
>
> **[Close]** Everything you saw — discovery, recruitment, hand-offs, supervision, the eject — flowed through Band. **Band turns eight agents into a coordinated team; Leash makes that team safe enough to aim at a real target.**

---

## 4. Video structure (record these, then voice over)

| # | ~Time | On screen (record) |
|---|---|---|
| 1 | 0:00–0:22 | Title card → Control Center b-roll |
| 2–3 | 0:22–1:25 | Slides: problem → architecture (the Band diagram) |
| 4 | 1:25–1:40 | **Band room (app.band.ai):** all 8 agents present |
| 5 | 1:40–2:05 | Band room: kickoff @mention → Commander delegates to ScopeWarden/Auditor/Recon |
| 6 | 2:05–2:30 | Band room: Recon reports → Commander **recruits the SQLi Hunter** into the room |
| 7 | 2:30–2:55 | Band room (intent @operator) → **Control Center** (APPROVE click) |
| 8 | 2:55–3:08 | Control Center: finding lands; (optional) kill-switch ejects specialists |
| 9 | 3:08–3:20 | Terminal: `make verify` → `Chain OK — N events, no tampering detected` |
| 10 | 3:20–3:30 | Title card: tagline + Band |

---

## 5. JOSH — run the demo on your computer

Goal: a clean screen recording of the **live 8-agent run in the Band room** + the
**Control Center**. Record silently, then Augie/you voice over Section 3.

### 5.0 Prerequisites
- `uv` (https://docs.astral.sh/uv/), Docker Desktop, a screen recorder (macOS ⌘⇧5, or OBS).
- A **Band account** at app.band.ai and an **`ANTHROPIC_API_KEY`** (Anthropic console).

### 5.1 Get the code
```bash
git clone https://github.com/AugieBarr/Leash-AB-JL.git
cd Leash-AB-JL
git checkout claude/charming-allen-jiphaq      # (or main, if it's been merged)
make install                                    # uv sync --extra dev
make proof                                       # sanity: lint + 98 tests + 1000-job scale, all green
```

### 5.2 Register the 8 agents (once, one Band account)
At app.band.ai, create eight agents (New Agent → Remote/External) and copy each
`agent_id` + `api_key`. Register all under ONE account so they're siblings:
```
leash-commander   leash-scope-warden  leash-auditor    leash-recon-scout
leash-sqli-hunter leash-xss-hunter    leash-auth-breaker  leash-reporter
```

### 5.3 Fill the secrets (gitignored — never committed)
```bash
cp env.example .env                              # set ANTHROPIC_API_KEY
cp agent_config.example.yaml agent_config.yaml   # fill the 8 agent_id + api_key pairs
```

### 5.4 Connectivity check (no Anthropic key needed)
```bash
make boot-check        # expect "8/8 agents online" — if not, the failing label is printed
```

### 5.5 Stage the live run (three terminals)
```bash
# terminal 1 — lab target
make juice-up                                    # OWASP Juice Shop on :3000
# terminal 2 — Control Center (record this window)
make viewer                                      # http://localhost:8089/?engagement=demo-01
# terminal 3 — the swarm
make live                                        # python -m swarm.launcher --engagement-id demo-01
```
Open the Band room at app.band.ai/chat with all 8 agents added, then kick off (either
`make seed` in a 4th terminal, or type it in the Band UI):
```
@leash-commander Begin the authorized engagement against localhost:3000 (OWASP Juice Shop).
```

### 5.6 Record
1. **Dry run once** end-to-end so you know the beats and timing.
2. **Clean take:** screen-record the **Band room** (agents coordinating, the Commander
   recruiting the SQLi Hunter) and the **Control Center** (the gate → APPROVE → the
   finding landing + VERIFIED badge). Capture generously; you'll cut.
3. Closing shot — a clean terminal:
   ```bash
   make verify        # Chain OK — N events, no tampering detected
   ```
4. In the editor, **speed up agent think-time 2–4×**; keep the @mention and
   recruit-into-room moments at full speed (those are the money shots).

### 5.7 If the live run is flaky (deterministic fallbacks — always work, no API key)
These are real, repeatable, and fast — use them as b-roll or a backup spine:
```bash
make control-demo      # real recon + a live web-driven approval gate (in a 2nd terminal: make viewer)
make demo              # full governed pipeline vs Juice Shop → seals + verifies a bundle
make tamper-demo       # flips one signed event → VERIFIED flips to TAMPERED in the viewer
make proof             # governance + 1000-job scale, green, with zero setup
```

### 5.8 Troubleshooting (quick)
| Symptom | Fix |
|---|---|
| `boot-check` < 8/8 | an `agent_config.yaml` entry is wrong, or an agent isn't under the same Band account (the failing label is printed) |
| "ANTHROPIC_API_KEY is not set" | set it in `.env` (the live LLM run needs it; `boot-check` doesn't) |
| "Juice Shop not reachable" | Docker not running / image still pulling — `make juice-up`, wait ~20s, retry |
| viewer won't bind :8089 | another viewer is running — `python -m viewer.viewer --port 9000` |
| agents connect but idle | make sure the kickoff `@leash-commander` was actually posted (`make seed` or type it in Band) |

---

## 6. Submission checklist
- [ ] Project title + tagline (§1)
- [ ] Short + long descriptions (§1)
- [ ] Tech / category tags (§1)
- [ ] Cover image — Control Center frame (§1)
- [ ] Slide deck PDF (§2)
- [ ] Demo video MP4 ≤5 min (§3–4)
- [ ] Public GitHub repo (link above) + required session/tooling report
- [ ] Application URL (§1)
