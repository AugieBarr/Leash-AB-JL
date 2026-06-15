# Leash — Demo Run Sheet (the clean take)

A clean **&lt;3:00** recording. The spine is **deterministic** (no live LLM, no API
key, no flake); the two Band beats are captured and intercut. Every known gotcha is
sequenced out below. [`DEMO.md`](DEMO.md) holds the shot-by-shot + narration; this is
the operational map.

**Golden rule:** every command has worked on a dry run *before* the recording starts —
flakes surface now, not on camera.

---

## Pre-flight — the state to reach before recording

```bash
cd ~/code/active/leash
uv sync --extra dev                          # deps present
docker compose up -d --wait juice-shop       # blocks until the target is serving
curl -s localhost:3000 | grep -q OWASP && echo "target ready"
```

Each beat verified once on a dry run (the single most load-bearing step):

```bash
python scripts/control_demo.py               # terminal B; viewer in terminal A; APPROVE in the browser
python scripts/tamper_demo.py --source control-demo   # expects: "TAMPERED — bad signature at seq N"
python scripts/seal_to_band_demo.py          # the room shows an "AUDIT SEALED — …" message
```

Windows arranged: **Control Center** full-screen (browser), **one terminal** visible,
the **Band room** (https://app.band.ai/chat) in a tab. Notifications silenced. Terminal
font large.

---

## The recording

The **spine** (Segments 1–3) is one continuous terminal+browser take — deterministic,
so a single take is realistic. The **Band seal** (Segment 4) is captured separately and
intercut as the close.

### Segment 1 — the governed pipeline + the leash holds  (~0:00–1:40)
```bash
# Terminal A — the operable Control Center
python -m viewer.viewer --engagement control-demo
#   open  http://localhost:8089/?engagement=control-demo  full-screen

# Terminal B — the paced engagement
python scripts/control_demo.py
```
On screen: recon streams in, then the scope guard blocks `leash-sqli-hunter → /ftp` —
the Governance Holds panel ticks. *The leash holds.* (A beat held here reads well.)

### Segment 2 — the human gate  (~1:40–2:10)
The in-scope probe opens the gate itself. The operator's **APPROVE** in the browser
(held ~3s) confirms SQLi → a HIGH finding lands → the bundle seals. *Nothing destructive
runs without a human — and that approval is itself sealed into the chain.*

### Segment 3 — you cannot forge it  (~2:10–2:35)
```bash
# control_demo has already sealed control-demo
python scripts/tamper_demo.py --source control-demo
#   on screen: "TAMPERED — bad signature at seq N"
```
The second tab at `http://localhost:8089/?engagement=tamper-demo` flips to a **TAMPERED**
badge, the altered event **red** (held ~3s).

### Segment 4 — the close: the seal lands in Band  (~2:35–3:00)
```bash
python scripts/seal_to_band_demo.py          # then the Band room tab
```
The Auditor's machine-posted **`AUDIT SEALED — <hash>`** message appears in-channel.
*The proof isn't just written to disk — it's posted into the room, as an event. It lands
where the swarm lives. **You cannot forge this record. Leash — governed, on Band.***

> An optional live-recruit intercut: the live swarm
> (`python -m swarm.launcher --engagement-id demo --seed --brain-only`) shows the Commander
> recruiting the Recon Scout — good for ~10s at the top. It's slow and nondeterministic, so
> it stays a bonus, never the spine; the seal-in-room beat is the reliable Band proof.

---

## Failure guards

| Symptom | Resolution (state reached) |
|---|---|
| a script reports **"Juice Shop not reachable"** | a ~20s wait + rerun clears it; the `curl` above confirms readiness |
| `tamper_demo` reports **"No sealed engagement"** | the seal was skipped — `control_demo.py` + an APPROVE produces it first (or `offline_demo.py`, then `tamper_demo.py` with no `--source`) |
| **`seal_to_band_demo.py` flakes** (Band network/creds) | the close falls back to `python -m governance.verify engagements/control-demo/control-demo_bundle.tar.gz` → **"Chain OK"**. The terminal verify is the offline proof; the Band message is the live proof — either one closes the thesis |
| the viewer sits at **"waiting for first event"** | the `?engagement=` is wrong — `control-demo` for the spine, `tamper-demo` for the red beat |
| the live swarm stalls | it's optional — the deterministic spine carries the whole demo on its own |

---

## Pitfalls (observed)

- The live LLM swarm is slow, nondeterministic, and burns the Claude subscription — the deterministic spine carries the demo, so the swarm stays an optional bonus intercut.
- The honest scale phrasing is "1000 concurrent worker **tasks**," never "1000 agents."
- A single spine take + the seal-in-room intercut reads cleaner than 5 spliced clips; trimming dead air is the only edit needed.
