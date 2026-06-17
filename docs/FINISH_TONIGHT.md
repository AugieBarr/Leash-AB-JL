# Finish tonight — submission checklist

Five steps, in order. Each notes **who**, the **exact** commands/clicks, and the
**done-when** signal. Target: locked tonight (hard deadline 2026-06-19 11:00 AM ET).

All submission copy lives in [`SUBMISSION.md`](SUBMISSION.md); the full demo script
is in [`RUNSHEET.md`](RUNSHEET.md).

---

## Step 1 — Repo visibility  *(Augie · ✅ done)*

- State: **public** — confirmed at https://github.com/AugieBarr/Leash-AB-JL.

---

## Step 2 — Demo video  *(Josh · ~30 min incl. retakes)*

- Current state: **not recorded**. Target ≤ 3:00.
- Windows: **Control Center** (browser, full-screen) + a **terminal** + the **Band
  room** tab (https://app.band.ai/chat).
- Framing (the judge's lens — don't undersell Band): Band is **load-bearing** — it
  is the agent event loop, `@mention` dispatch, live recruit, and the surface a
  second framework (Aegis) joins. The in-process scope/gate/audit are the
  *enforcement* that survives a Band outage. The line is **"Band coordinates; code
  enforces"** — never "Band is where we log what happened."

Pre-flight (green before recording):
```bash
cd ~/code/active/leash
colima start                                   # if docker isn't up
docker compose up -d --wait juice-shop
curl -s localhost:3000 | grep -q OWASP && echo "target ready"
uv sync --extra dev
python connect_test.py                         # expect "10/10 agents connected" before any live Band beat
(cd aegis && mix escript.build)                # builds ./aegis/aegis
```

Rehearsal (one pass before the recorder is on — flakes surface off-camera, not on it):
```bash
python scripts/control_demo.py                      # APPROVE in the browser → SQLi confirmed + sealed
python scripts/tamper_demo.py --source control-demo # expect "TAMPERED — bad signature at seq N"
python scripts/seal_to_band_demo.py                 # the room shows "AUDIT SEALED — <hash>"
```

The beats (one take each; trim dead air after):

**Beat 1 — Band room, coordination is live** *(the most important shot)*
```bash
python -m swarm.launcher --engagement-id demo --seed --brain-only
```
On screen: the Band room tab — the Commander **recruiting the Recon Scout**, the
**@mention handoffs** appearing. ~20–30s. *(This is the "agents coordinate through
Band during the workflow" proof — the one beat not to skip.)*

The live swarm is slow and nondeterministic, so this clip is captured **on its own**
and intercut: it's run until it behaves, then that take is used. Essential footage —
but separate from the single continuous spine take (Beats 3–4), which is deterministic.

**Beat 2 — Cross-framework, a second runtime attests**
```bash
./aegis/aegis attest --restrict-paths /rest/products --dry-run   # Elixir re-derivation + attestation
export AEGIS_API_KEY=$(.venv/bin/python -c "from band.config import load_agent_config; print(load_agent_config('leash-auditor')[1])")
./aegis/aegis check                                              # live Elixir → Band auth, HTTP 200
```
On screen: the `🛡️ AEGIS (Elixir/OTP) attests …` line, then `✓ authenticated to Band …
HTTP 200`. Voiceover: *a separate Elixir runtime — zero shared code with the Python SDK
— re-derives the grant and authenticates to Band live. Cross-framework, for real.*

**Beat 3 — The leash holds + the human gate** (deterministic spine)
```bash
# 1) terminal A — viewer first, then open the browser full-screen
python -m viewer.viewer --engagement control-demo
#      open http://localhost:8089/?engagement=control-demo
# 2) terminal B — then the paced engagement
python scripts/control_demo.py
```
On screen: the scope guard blocks `→ /ftp` (Governance Holds ticks); the gate opens
→ **APPROVE** click in the browser → SQLi confirmed → HIGH finding lands.

**Beat 4 — The record cannot be forged**
```bash
python scripts/tamper_demo.py --source control-demo
#   open http://localhost:8089/?engagement=tamper-demo
```
On screen: the badge flips **VERIFIED → TAMPERED**, the bad event lights red.

**Beat 5 — The seal lands in Band**
```bash
python scripts/seal_to_band_demo.py
```
On screen: the Band room shows the machine-posted `AUDIT SEALED — <hash>` message.
Fallback if Band flakes: `python -m governance.verify engagements/control-demo/control-demo_bundle.tar.gz` → "Chain OK".

- Done when: a single ≤3:00 video file exists.

---

## Step 3 — Video: export an MP4 (the form wants a FILE, not a link)  *(Josh · 5 min)*

- **Confirmed against the live form (2026-06-16):** the **Video Presentation** field on
  Step 2 is a direct **file upload**, not a URL paste — so export the recording to an
  **`.mp4`** (most editors: Share → Export → 1080p). Keep the file reasonably small.
- A **Loom / YouTube unlisted** link is still worth having: it most likely feeds the
  **Application URL / Demo Platform** field on the form's Step 3 (that step is gated
  behind the Step-2 uploads, so it couldn't be inspected yet — confirm when you reach it).
- Done when: a local `leash-demo.mp4` exists and plays.

---

## Step 4 — Slide deck export  *(Josh · 5 min)*

```bash
cd ~/code/active/leash
npx @marp-team/marp-cli docs/slides.md --pdf   # → docs/slides.pdf
```
(or `docs/slides.md` in VS Code with the **Marp** extension → Export PDF.)

- Done when: `docs/slides.pdf` exists and reads cleanly.

---

## Step 5 — Submission form  *(Josh · 10 min)*

The form is **3 steps** and **auto-saves a draft** (look for "Last saved at …" / a %
bar). **Step 1 (Basic Information) is already drafted and saved** — title, short + long
description, category (**Security**), event track (**Regulated & High-Stakes
Workflows**), and the five Technologies (**Band Agentic Mesh / Band Integrations / Band
Control Plane / Anthropic Claude / Claude Code** — Python/Elixir aren't in their curated
list, so the five Band+Claude tags are the accurate set). Verify it, then do Steps 2–3:

**Step 2 — Media (all three are FILE UPLOADS via the native picker):**

| Field | File | Required |
|---|---|---|
| Cover Image | `docs/img/cover.png` (drag-drop) | optional |
| Video Presentation | `leash-demo.mp4` (Step 3) | **yes** |
| Slide Presentation | `docs/slides.pdf` (Step 4) | **yes** |

> **The form's Step 3 is gated** behind the two required Step-2 uploads — it can't be
> reached until the video + slides are in. It most likely holds the **GitHub repo URL**
> (https://github.com/AugieBarr/Leash-AB-JL) and the **Application / Demo URL** (the Loom
> link). Fill those there, then submit.

Long-form copy, if you ever need to re-enter Step 1, lives in [`SUBMISSION.md`](SUBMISSION.md).

- Done when: the form is submitted and the confirmation shows.

---

## Note — `leash-aegis` dedicated handle needs a Band plan upgrade

A dedicated `leash-aegis` Band identity would let Aegis post its attestation into the
live room under its own name. Band's remote-agent limit is **reached (10/10) on the
current plan** — registering an 11th requires a paid upgrade. This is cosmetic: Beat 2's
`--dry-run` + `./aegis/aegis check` (live Elixir→Band auth, HTTP 200) already prove a
real, separate Elixir runtime coordinating with Band. If the plan is upgraded later,
`leash-aegis` registers via the same flow as the other ten and posts live in-room.
