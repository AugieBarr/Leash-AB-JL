# Leash — Demo Video Script & Screen-Recording Plan

For the lablab.ai **Band of Agents** submission video (MP4, ≤5 min). Structure
follows the lablab format — **intro → slides → live functionality** — and is
engineered to the judging rubric, which is explicitly Band-coordination-centric.

**Target length: ~3:30** (well under the 5-min cap; judges' attention drops past
~4 min). Record silently, then voice over — see *Production* at the bottom.

> The hero of this video is the **Band room**. Every governance beat is narrated
> back to "…and this happens *through Band*." The judging criterion that matters
> most — Application of Technology — asks for *agents collaborating through Band
> with task handoffs, shared context, role specialization, task state, and
> coordination*. The demo is staged so each of those words is literally on screen.

---

## 1. Storyboard

| # | ~Time | ON SCREEN (record this) | Rubric beat |
|---|---|---|---|
| 1 | 0:00–0:22 | Title card → fast cuts: ungoverned-agent headlines, then the Leash Control Center | Hook / Business value |
| 2 | 0:22–0:50 | **Slide:** problem (autonomous offense has no governance) | Business value, Presentation |
| 3 | 0:50–1:25 | **Slide:** the architecture diagram — 8 roles, "Band = coordination layer" | Role specialization, Presentation |
| 4 | 1:25–1:40 | **Band room (app.band.ai):** all 8 agents present in the room | Presence / coordination |
| 5 | 1:40–2:05 | Band room: operator's kickoff `@leash-commander` → Commander delegates to `@scope-warden`, `@auditor`, `@recon-scout` | **Task handoffs**, role specialization, **task state** |
| 6 | 2:05–2:30 | Band room: Recon reports findings to the Commander; Commander **recruits the matching specialist** (`@leash-sqli-hunter` added to the room) | **Agents discover each other / divide work** (Originality) |
| 7 | 2:30–2:55 | Split: Band room (SQLi Hunter posts intent, `@operator`) → **Control Center** (operator clicks APPROVE) | **Escalation / review**, human-in-the-loop, **shared context** (signed chain) |
| 8 | 2:55–3:08 | Control Center: vulnerability lands in the live feed; (optional) Commander kill-switch **ejects specialists from the room** | Coordination, control |
| 9 | 3:08–3:20 | Terminal: `make verify` → `Chain OK — N events, no tampering detected` | Verifiable output / trust |
| 10 | 3:20–3:30 | Title card: tagline + Band logo | Close |

---

## 2. Voiceover script (read this into the mic)

Spoken word count ≈ 410 (~120 wpm over the cut — unrushed). Bracketed cues are
*not* spoken.

**[1 — Hook]**
> Enterprises want autonomous agents to find their security holes. But nobody
> will point an AI swarm at production — because today's offensive agents have no
> governance. No scope. No audit trail. No human in the loop. XBOW's own CISO
> calls it a chaos phase, with agents "dropping your tables." **Leash fixes that —
> a governed offensive-security swarm, built on Band.**

**[2 — Problem slide]**
> Penetration testing is exactly the kind of work you'd want a multi-agent system
> to do: map a target, divide the work across specialists, exploit, and report.
> The blocker has never been capability — it's *control*. An enterprise can't run
> what it can't scope, supervise, and audit.

**[3 — Architecture slide]**
> Leash is eight specialized agents that coordinate through a **Band room — and
> Band is the coordination layer.** It gives every agent an identity, a persistent
> connection, and @mention routing, so the swarm hands work off without flooding
> each other. A Commander orchestrates. A ScopeWarden issues each agent a
> capability it cannot exceed. An Auditor keeps a tamper-evident record. A Recon
> Scout maps the surface. And three offensive specialists — SQL injection,
> cross-site scripting, and authentication bypass — each join only when they're
> needed.

**[4 — Band room, the swarm]**
> Here's a live engagement. Eight agents, each connected to Band, sharing one
> room. This room *is* the shared context — every message, every hand-off, every
> decision happens here, in the open, where the human can see it.

**[5 — Kickoff + delegation]**
> The operator starts it with a single @mention to the Commander. The Commander
> delegates — it asks the ScopeWarden to set scope, the Auditor to open the audit
> chain, and recruits the Recon Scout to map the target. Every hand-off is an
> @mention; every agent wakes only when it's called.

**[6 — Recruit-on-discovery]**
> Recon reports back — and flags a SQL-injection surface. That's the trigger.
> The Commander recruits the *matching* specialist — the SQLi Hunter — into the
> room, live. This is the part a script can't do: **the swarm assembles itself
> around what it discovers.** A different finding would pull in a different
> specialist.

**[7 — The gate / escalation]**
> But before it exploits anything, the SQLi Hunter posts its intent and escalates
> to the human. The operator approves from the Control Center — and that approval
> is **signed into the shared audit chain**, bound to who approved what. This gate
> is enforced in code, not a prompt the agent could talk its way around.

**[8 — Confirm + kill-switch]**
> The exploit runs, the vulnerability is confirmed, and it lands in the live feed.
> And if anything ever looks wrong, the Commander's kill-switch ejects every
> specialist from the Band room instantly — coordination *and* a hard stop.

**[9 — Verify]**
> When it's done, the Auditor seals a bundle that anyone can verify — from the
> public key alone, with no access to the swarm. Chain OK. Nothing added, altered,
> or removed.

**[10 — Close]**
> Everything you saw — discovery, recruitment, hand-offs, supervision, the eject —
> flowed through Band. **Band turns eight agents into a coordinated team; Leash
> makes that team safe enough to aim at a real target.** Governed autonomy — that's
> what finally lets enterprises put agents to work on security.

---

## 3. Shot-capture checklist (stage this before recording)

Pre-flight (see `docs/RUNBOOK.md` for detail):
1. Register the 8 agents at app.band.ai (one account). Fill `.env` + `agent_config.yaml`.
2. `make boot-check` → confirm **8/8** online.
3. `make juice-up` (Juice Shop on :3000).
4. `make viewer` (Control Center on :8089) — open `?engagement=demo-01`.
5. `make live` (the swarm) in another terminal.
6. Have the Band room open at app.band.ai/chat with all 8 agents added.

Capture, per segment:
- **Band room footage (segments 4–8):** screen-record the app.band.ai room. Do a
  full run first as a dry run, then a clean take. Capture *generously* — you'll cut.
- **Control Center (segments 7–8):** record `localhost:8089` — the gate prompt, the
  APPROVE click, the findings feed, the VERIFIED badge.
- **Verify (segment 9):** a clean terminal running `make verify`.
- **Slides (segments 2–3):** screen-record the PDF deck, or drop in static slide PNGs.

> **Handle dead time:** live agents have think/latency gaps. In the editor, speed
> those 2–4× (or hard-cut) so the *coordination* reads fast. Keep the @mention and
> add-participant moments at full speed — those are the money shots.

---

## 4. Rubric coverage map (self-check before you submit)

| Judging phrase | Where the video proves it |
|---|---|
| "uses Band as the coordination layer" | Segments 3, 4, 5, 6, 8, 10 — stated and shown |
| "clear task handoffs" | Segment 5 (Commander → ScopeWarden/Auditor/Recon via @mention) |
| "shared context" | Segment 4 (the room) + Segment 7 (the signed audit chain everyone writes to) |
| "role specialization" | Segment 3 (8 distinct roles) + the specialists only acting in-domain |
| "task state, coordination" | Segment 5–8 (the Commander orchestrates; the audit chain is the durable task record) |
| "agents discover each other, divide work" (Originality) | Segment 6 (recruit-on-discovery — the differentiator) |
| "review outputs, escalate issues" (Originality) | Segment 7 (escalation to the human gate) + Auditor seals/verifies |
| "real enterprise workflow" (Business value) | Segments 1, 2, 10 (governed pentest a regulated org could actually run) |
| "make the workflow easy to understand" (Presentation) | Slides 2–3 + every beat narrated back to Band |

---

## 5. Companion deliverables (not the video, but referenced by it)

- **Cover image (16:9):** the Control Center dashboard mid-engagement (roster +
  live findings + VERIFIED badge) — it's the most striking single frame.
- **Slide deck (PDF):** problem → solution → architecture (the Band diagram) →
  live results → business value (TAM/SAM, the governance gap as the wedge) → team.
- **Application URL:** the Control Center is a zero-dependency web app — a deployed
  read-only instance (or the offline/control demo) can serve as the interactive link.
