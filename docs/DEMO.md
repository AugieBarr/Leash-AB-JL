# Leash — 3-Minute Demo Storyboard

The video is what the judges actually score. This is the shot-by-shot for a ~3:00
run. Two beats carry it: **the leash holds** (scope guard blocks an off-target
reach, live) and **the trail can't be forged** (tamper-evidence flips the badge
red). Everything else sets those up.

**Setup before recording**
- `docker compose up -d juice-shop` (target on :3000)
- Terminal A: `python -m viewer.viewer --engagement control-demo` → open `http://localhost:8089/?engagement=control-demo` full-screen
- Terminal B ready with `python scripts/control_demo.py` and `python scripts/tamper_demo.py`
- Live-swarm version (preferred): a Band room open with the six agents + `python -m swarm.launcher` (needs `ANTHROPIC_API_KEY`). If the live run is flaky, fall back to `control_demo.py` as the on-screen "swarm" and narrate the Band room separately.

---

| Time | On screen | Narration (tight) |
|---|---|---|
| **0:00–0:18** | Control Center title, dark UI | "Autonomous pentest agents are here. The field calls it a chaos phase — agents *dropping your tables*, no audit trail, no scope enforcement. Leash is the **governed** swarm: safe to run unsupervised." |
| **0:18–0:50** | Band room: Commander opens the engagement, recruits Recon Scout; ScopeWarden issues a scoped capability. Roster lights up live. | "Six agents coordinate **through a Band room**. The Commander recruits specialists as the surface is discovered; the ScopeWarden hands each one a capability it cannot exceed." |
| **0:50–1:18** | Live Findings feed fills (misconfig, exposures); VERIFIED badge + chain tail advancing | "Recon maps the target. Findings stream in — each one **hash-chained, Ed25519-signed, and re-verified the instant it lands.**" |
| **1:18–1:42** | **Defenses panel** ticks up: scope guard blocks `leash-sqli-hunter → /ftp` | "The SQLi specialist is scoped to `/rest/products`. Watch it reach for `/ftp` — **blocked.** Not by trust. By construction. The leash holds." |
| **1:42–2:18** | Gate opens (amber) → operator clicks **APPROVE** → SQLi confirmed 200→500, HIGH finding lands; gate turns green | "Nothing destructive runs without a human. The operator approves **in the browser** — and that approval is itself recorded into the tamper-evident chain. SQL injection confirmed." |
| **2:18–2:52** | Run `tamper_demo.py`; reload viewer on `tamper-demo`: badge flips **VERIFIED → TAMPERED**, event #6 goes red | "Every tool claims an audit log. Watch someone try to **rewrite** ours — erase the SQLi finding. One byte changed. Caught instantly, with only the **public key**. You cannot forge this record." |
| **2:52–3:00** | Sealed bundle + `python -m governance.verify … → Chain OK` | "Leash: the coordination and control plane that makes an offensive swarm safe to run unsupervised. Built on Band." |

---

**Direction notes**
- Lead with the *problem* (governance gap), not the architecture. Judges remember the two demos, not the diagram.
- The APPROVE click and the badge flipping red are the two "lean in" moments — hold on each for a beat, don't rush.
- Keep the terminal visible when running `tamper_demo.py` so the `TAMPERED — bad signature at seq 6` line reads on screen alongside the red UI.
- If recording the live Band swarm: show the actual `@mention` handoffs in the room — that's the Band-coordination proof judges want. Cut to the dashboard for the findings/gate/tamper beats.
- Fallback ordering if the live swarm misbehaves: record the dashboard run (`control_demo.py`) first as the spine, then capture the Band room separately and intercut — the governance story is identical either way.
