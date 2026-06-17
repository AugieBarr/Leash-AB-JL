# Finish tonight — submission checklist

Five steps, in order. Each notes **who**, the **exact** commands/clicks, and the
**done-when** signal. Target: locked tonight (hard deadline 2026-06-19 11:00 AM ET).

All submission copy lives in [`SUBMISSION.md`](SUBMISSION.md); the full demo script
is in [`RUNSHEET.md`](RUNSHEET.md).

---

## Step 1 — Repo visibility  *(Augie · 1 min)*

- Current state: **private**.
- Path: https://github.com/AugieBarr/Leash-AB-JL/settings → **Danger Zone** →
  "Change visibility" → "Make public" → confirm.
- Done when: the repo loads in a logged-out browser.

---

## Step 2 — Demo video  *(Josh · ~30 min incl. retakes)*

- Current state: **not recorded**. Target ≤ 3:00.
- Windows: **Control Center** (browser, full-screen) + a **terminal** + the **Band
  room** tab (https://app.band.ai/chat).

Pre-flight (green before recording):
```bash
cd ~/code/active/leash
colima start                                   # if docker isn't up
docker compose up -d --wait juice-shop
curl -s localhost:3000 | grep -q OWASP && echo "target ready"
uv sync --extra dev
(cd aegis && mix escript.build)                # builds ./aegis/aegis
```

The beats (one take each; trim dead air after):

**Beat 1 — Band room, coordination is live** *(the most important shot)*
```bash
python -m swarm.launcher --engagement-id demo --seed --brain-only
```
On screen: the Band room tab — the Commander **recruiting the Recon Scout**, the
**@mention handoffs** appearing. ~20–30s. *(This is the "agents coordinate through
Band during the workflow" proof — the one beat not to skip.)*

**Beat 2 — Cross-framework, a second runtime attests**
```bash
./aegis/aegis attest --restrict-paths /rest/products --dry-run
```
On screen: the `🛡️ AEGIS (Elixir/OTP) attests …` line. Voiceover: *a separate
Elixir runtime independently re-derives the grant — cross-framework, in the room.*

**Beat 3 — The leash holds + the human gate** (deterministic spine)
```bash
# terminal A
python -m viewer.viewer --engagement control-demo
#   open http://localhost:8089/?engagement=control-demo  (full-screen)
# terminal B
python scripts/control_demo.py
```
On screen: the scope guard blocks `→ /ftp` (Governance Holds ticks); the gate opens
→ **APPROVE** click in the browser → SQLi confirmed → HIGH finding lands.

**Beat 4 — The record cannot be forged**
```bash
python scripts/tamper_demo.py
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

## Step 3 — Video hosting  *(Josh · 5 min)*

- A **Loom** upload (or YouTube **unlisted**) gives a share link.
- That one link serves BOTH the **Video Presentation** field and the **Application
  URL / Demo Platform** fields.
- Done when: the link plays in an incognito window.

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

Fields paste straight from [`SUBMISSION.md`](SUBMISSION.md):

| Form field | Source |
|---|---|
| Project Title | SUBMISSION.md |
| Short Description | SUBMISSION.md |
| Long Description | SUBMISSION.md |
| Technology & Category Tags | SUBMISSION.md |
| Cover Image | `docs/img/cover.png` |
| Video Presentation | the Loom/YouTube link (Step 3) |
| Slide Presentation | `docs/slides.pdf` (Step 4) |
| Public GitHub Repository | https://github.com/AugieBarr/Leash-AB-JL |
| Demo Application Platform | the Loom/YouTube link |
| Application URL | the Loom/YouTube link |

- Done when: the form is submitted and the confirmation shows.

---

## Optional — register `leash-aegis` for a live cross-framework beat  *(Josh · 5 min)*

Lets Aegis post its attestation into the **live** Band room on camera (vs the dry-run).

- A new agent `leash-aegis` registered at app.band.ai (same flow as the other ten),
  its `agent_id` + `api_key` added to `agent_config.yaml`, added to the room.
- During recording:
  ```bash
  export AEGIS_API_KEY=...        # leash-aegis key
  ./aegis/aegis attest --room <room-id> --restrict-paths /rest/products
  ```
  The `🛡️ AEGIS …` attestation then appears in the Band room as a governance event.
