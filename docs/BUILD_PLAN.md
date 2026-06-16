# Leash — A Governed Offensive Agent Swarm on Band

**Band of Agents Hackathon · Team Roan (Josh + Augie) · lablab.ai**
**Submission deadline: 2026-06-19 11:00 AM ET. Today: 2026-06-14.**
*(Working name "Leash" — provisional; alternatives SwarmWarden / Basilisk. Sets the repo name once chosen.)*

---

## Context

Day-3 pivot away from the original "Casefile" fraud-desk concept toward **cybersecurity / pentesting on Band**, per Josh. The competitive landscape was mapped this session via web research; three forks resolved with Josh: **offense-forward positioning**, **web-app exploitation target**, **tiered swarm** scale model.

**The competitive finding** *(from web search, this session)*: autonomous multi-agent pentest is **saturated** — 39+ open-source agents across 6 architecture patterns ([AppSecSanta](https://appsecsanta.com/research/ai-pentesting-agents-2026)), XBOW at #1 on HackerOne, HexStrike-AI orchestrating 150+ tools through one MCP brain ([Check Point](https://blog.checkpoint.com/executive-insights/hexstrike-ai-when-llms-meet-zero-day-exploitation/)). "Multi-agent pentest" is **table stakes, not a differentiator.**

But every source flags the **same unfilled gap — governance**: XBOW's own CISO calls it a *"chaos phase… we are not ready,"* with agents *"dropping your tables"* ([SiliconANGLE/RSAC26](https://siliconangle.com/2026/03/25/autonomous-penetration-testing-enters-chaos-phase-ai-rewrites-offensive-security-rsac26/)); AppSecSanta: *"most tools prioritize autonomous execution over audit trails or scope enforcement."* That gap is **exactly what Band's primitives (human-gate, structured events, dynamic recruit) are built to fill** — and exactly Roan's brand (cybersecurity-first, audit/trust layer).

**Intended outcome:** a submittable, demoable, *winning* hackathon entry that is the **anti-HexStrike** — a swarm safe to run unsupervised because it carries a scope leash, a tamper-evident audit trail, and a human kill-switch, all coordinated through Band.

---

## Goal

A public MIT repo + 3-min demo where a tiered agent swarm coordinates through a Band room to find and exploit a real vulnerability on a deliberately-vulnerable target (OWASP Juice Shop), pausing at a human approval gate before exploitation, and emitting a tamper-evident, independently-verifiable audit bundle when the room closes.

---

## Differentiation thesis (the "why we win")

**Position: the Governed Swarm.** Not another autonomous hacker — the coordination + control plane that makes a swarm safe to run unsupervised. Band fills the five gaps the field admits to:

| Field's named gap | Band primitive it answers |
|---|---|
| No scope enforcement | `scope_guard` fail-closed allowlist + ScopeWarden capability gate |
| No audit trail | Every action → Band `send_event` → hash-chained ledger → sealed bundle |
| *"Dropping your tables"* | Human approval gate **before** any destructive tool; Commander kill-switch |
| Context overflow / lost long-session memory *(named tech gap)* | Tiered swarm of bounded-context specialists; Band holds durable shared context |
| Static recon→scan→exploit pipelines | **Dynamic recruit-on-discovery** — recon finds SQLi → SQLi specialist joins the room live |

**On contact:** vs **XBOW** (closed, single-vendor — no coordination story to build on); vs **HexStrike** (ungoverned threat-actor tool — Leash is its governed opposite). Band's `@mention` routing means a 30-agent room does not flood every agent (each wakes only when called) — so the tiered swarm *fits* Band's model rather than fighting it.

**Contest fit** (judging axes, from 06-09 live read): coordination-layer (dynamic recruiting under real stakes = boldest possible Band use); originality (almost no team dares offense; none pairs it with a trust layer); business value (governance is the #1 enterprise blocker to autonomous offense); presentation (swarm visibly hunting + human hitting *approve* = strong video). Track 3 literally lists *"cybersecurity investigation workflows."*

---

## Architecture

```
                       BAND CASE ROOM  (every agent = persistent WS; humans see ALL messages)
  TIER 0  Human Operator (Josh/Augie) — @mentioned at approval gates; kill-switch; full audit view
  TIER 1  BRAIN AGENTS (persistent WS, Sonnet)
          Commander (orchestrate/recruit)   ScopeWarden (capabilities)   Auditor (chain + seal)
  TIER 2  SPECIALISTS (recruited per-discovery, Sonnet)
          Recon Scout   SQLi Hunter   XSS Hunter   Auth Breaker   Reporter
  TIER 3  WORKER TOOL-JOBS (asyncio tasks, NOT Band agents, Haiku/deterministic)
          http_probe · crawl · sqlmap · ffuf · jwt_crack   (semaphore-bounded fan-out)
```

**Room lifecycle (descriptive):**
1. **OPEN** — Commander creates the room and posts the engagement brief; ScopeWarden joins and issues the engagement capability (`localhost:3000` only); Auditor opens the hash-chain ledger for this `engagement_id`.
2. **RECON** — Commander `@recon-scout`; Scout runs `http_probe`/`crawl` worker-jobs and emits one `send_event(message_type="tool_result")` per finding; Auditor appends each to the chain.
3. **RECRUIT** — On a finding, Commander calls `band_add_participant("sqli-hunter")`; ScopeWarden derives a **restricted child capability** for that specialist (subset of engagement scope).
4. **GATE** — Before any exploit tool, the specialist posts `send_event(message_type="task", "APPROVAL REQUIRED…")` + `@operator approve/halt`, then blocks on the human's reply. "halt" → Commander `remove_participant` on all (kill-switch).
5. **EXPLOIT** — Specialist fans out worker tool-jobs; `scope_guard` wraps every subprocess (fails closed off-target); findings flow to Auditor.
6. **SEAL** — Commander `@auditor`; Auditor runs `verify_chain()`, exports the sealed bundle, posts the chain-tail hash to the room.
7. **CLOSE** — Commander removes all participants; the human runs an offline `verify` on the bundle.

**Ownership rule (de-risks recruiting):** all agents live under **one** Band account so they are *siblings* and recruit each other with zero contact-request friction. *[read from Band docs]*

---

## Agent roster

| Agent | Band id | Tier/Model | Role | Custom tools (CLI wrapped) |
|---|---|---|---|---|
| Commander | `leash-commander` | Sonnet | orchestrate, recruit, kill-switch | `open_case_room`, `close_case_room`, `issue_kill_switch` |
| ScopeWarden | `leash-scope-warden` | Sonnet | capability issuance | `issue_capability`, `check_capability` · `revoke_capability` *(stretch)* |
| Auditor | `leash-auditor` | Sonnet | chain writer + bundle sealer | `append_event`, `verify_chain`, `seal_bundle` |
| Recon Scout | `leash-recon-scout` | Sonnet | surface mapping | `http_probe`, `crawl_target`, `security_headers_probe`, `exposure_probe` · `js_enum` *(stretch)* |
| SQLi Hunter | `leash-sqli-hunter` | Sonnet | SQL injection | `run_sqlmap`, `manual_sqli_probe` |
| Reporter | `leash-reporter` | Sonnet | report synthesis | `render_findings_report`, `read_audit_bundle` |
| XSS Hunter **(built)** | `leash-xss-hunter` | Sonnet | reflected XSS | `manual_xss_probe` (approval-gated + scope-guarded; unit-tested) · `run_dalfox` *(stretch)* |
| Auth Breaker **(built)** | `leash-auth-breaker` | Sonnet | auth bypass (A07) | `manual_auth_bypass_probe` (approval-gated + scope-guarded; unit-tested) · `jwt_crack`, `idor_fuzz` *(stretch)* |

Worker tool-jobs are `asyncio.create_task` launched by specialists, semaphore-bounded, each gated by `scope_guard` before exec — **not** Band agents.

---

## Governance components (verified port specs)

All in `governance/` with **zero Band-SDK imports** (fully offline-testable). Clean-room MIT ports of Josh's hardened Elixir patterns.

**`audit_ledger.py`** — port of `diogenes_core/audit_log.ex` *[read from file]*. NDJSON at `engagements/{id}/audit.ndjson`. Per-event:
```
sig        = Ed25519_sign(privkey, seq_be64 ‖ kind ‖ hash_prev ‖ payload)   # HMAC-SHA256 fallback if time-pressed
chain_hash = SHA256(seq_be64 ‖ kind ‖ hash_prev ‖ payload ‖ sig)            # next event's hash_prev binds to this
genesis hash_prev = b"\x00" * 32
```
`append()` holds an `asyncio.Lock` (the atomic `append_head` race-fix); `verify_chain()` re-derives each `chain_hash`, checks `hash_prev` linkage + signature, detects any middle-entry tamper. Ed25519 is preferred (pubkey ships in the bundle → anyone verifies without the secret = the stronger demo story); HMAC is the fallback.

**`capability.py`** — port of `hermes/themis.ex` `restrict/2` + `evaluate/3` *[read from file]*. `ScopeSpec{hosts, ports, paths}`. `issue_capability(parent, restriction)` = field-wise intersection (host glob `*`→single-label); any empty field → `EmptyScopeError` (deny-all sentinel; cannot tunnel a no-op cap). `check_capability(cap, target)` eval order: expired → empty-scope → host → port → path. Default-deny is structural.

**`scope_guard.py`** — port of `diogenes_core/egress.ex`. `scope_guard(url, cap)` parses host via `urllib.parse`; empty/unparseable host fails closed; no allowlist match → `ScopeViolationError` (raised, not caught in normal flow). Invoked inside `tools/_subprocess.py:scoped_run` before every exec (the ToolBridge pre-hook port).

**`bundle.py`** — port of `polis_code_memory/attested_store.ex` seal. `export_bundle(id)`: runs `verify_chain()` (refuses to seal a tampered chain) → writes manifest `{id, target, times, chain_tail_hash, event_count, findings}` → tars NDJSON + manifest + pubkey → emits `.sha256`. Offline CLI `python -m leash.governance.verify <bundle.tar.gz>` → `Chain OK — N events, no tampering`.

**Human approval gate** *(now enforced in code, not on trust)* — the offensive tools call `enforce_gate` (`swarm/control_channel.py`), which opens a gate in the operator's Control Center and BLOCKS until the operator clicks APPROVE; a HALT or a timeout makes the tool refuse in-process and engages the kill-switch (it never defaults open). The SQLi Hunter's prompt still narrates the request in-room (`@operator` + the exact action), but the gate no longer depends on the model honouring it. Each approval is bound into the tamper-evident chain as a signed `approval` event (who approved what), and `watch_halt` runs alongside the live swarm so the Control Center kill-switch is live throughout.

---

## Repo layout (new MIT repo `leash/`)

```
leash/
  README.md  LICENSE(MIT)  pyproject.toml(uv)  docker-compose.yml(juice-shop:3000)
  .env.example  agent_config.example.yaml          # agent_config.yaml + .env gitignored
  agents/      base_agent.py commander.py scope_warden.py auditor.py
               recon_scout.py sqli_hunter.py reporter.py [xss_hunter.py auth_breaker.py]
  governance/  scope_guard.py capability.py audit_ledger.py bundle.py   # NO band-sdk imports
  tools/       recon_tools.py sqli_tools.py report_tools.py _subprocess.py(scoped_run)
  swarm/       launcher.py concurrency_cap.py engagement.py
  scale_test/  register_agents.py connect_harness.py worker_fanout_bench.py README.md
  viewer/      viewer.py                              # stretch: FastAPI SSE tailing audit.ndjson
  tests/       test_scope_guard.py test_capability.py test_audit_ledger.py test_concurrency_cap.py
  engagements/ .gitkeep                               # gitignored runtime data
```

**Stack** *(from Band docs)*: Python 3.11+, `uv`. `band-sdk[anthropic]` (import `thenvoi`), `cryptography`, `pydantic`, `httpx`, `pytest`. Agent pattern: `AnthropicAdapter(model="claude-sonnet-4-5-20250929", additional_tools=[(InputModel, handler)…], enable_execution_reporting=True)` → `Agent.create(adapter, agent_id, api_key, ws_url, rest_url)` → `await agent.run()`. `.env`: `THENVOI_REST_URL=https://app.band.ai/`, `THENVOI_WS_URL=wss://app.band.ai/api/v1/socket/websocket`, `ANTHROPIC_API_KEY`. Default adapter = **AnthropicAdapter** (simplest, most controllable); ClaudeSDKAdapter is the alt if per-agent MCP-tools + `cwd` sandbox are wanted.

---

## Reuse map (Elixir pattern → Python port)

| Need | Source pattern *(read this session)* | Port |
|---|---|---|
| Audit chain | `diogenes_core/audit_log.ex` | `governance/audit_ledger.py` (Ed25519/HMAC) |
| Capability ACL | `hermes/themis.ex` restrict/evaluate | `governance/capability.py` |
| Scope chokepoint | `diogenes_core/egress.ex` (fail-closed) | `governance/scope_guard.py` |
| Sealed bundle | `polis_code_memory/attested_store.ex` verify_chain | `governance/bundle.py` |
| Concurrency cap | `polis_code_dispatch/.../concurrency_cap.ex` (slot freed by task death) | `swarm/concurrency_cap.py` (`asyncio.Semaphore` + `add_done_callback`) |
| Tool wrapping + pre-hook | `polis_code_dispatch/tool_bridge.ex` | `tools/_subprocess.py:scoped_run` |
| Worker isolation | `.../worktree.ex` / `polis_rsi/.../isolated_copy.ex` | temp-dir per worker (worktree overkill for tool-jobs) |

All MIT-clean (no Dilithium NIF / Logos dep). The chain formula above is exact — any deviation breaks offline verification.

---

## Build schedule (Jun 14 → 19) — stated as end-of-block outcomes

**MVP line (the bar for a submittable demo):** Commander + ScopeWarden + Auditor + Recon Scout + SQLi Hunter in one Band room; `scope_guard` enforced; capability issuance live; hash-chained ledger + offline `verify_chain`; human approval gate before sqlmap; sealed bundle + verify CLI; one real SQLi flag on Juice Shop; the full 6-beat demo runs.

- **Tonight (Jun 14) — de-risk the unknowns first.** Repo + MIT + `uv` env exist. All agents registered at app.band.ai under ONE account → `agent_config.yaml` (this is what surfaces any Band quota — the #1 risk). Juice Shop running under docker; `curl localhost:3000` green. `governance/audit_ledger.py` first cut done; `tests/test_audit_ledger.py` tamper test green.
- **Jun 15 (lighter — $40k signing + billing split).** `scope_guard.py` + `capability.py` + `bundle.py` + their tests green. `agents/base_agent.py` (adapter wiring + `approval_gate`) done. Auditor connected to a live Band room, WS stable for 10 min (first live integration confirmed). *Augie: pitch narrative + demo-script + deck outline drafted.*
- **Jun 16.** `tools/recon_tools.py` + `_subprocess.py`, `agents/recon_scout.py`, `agents/commander.py` (open room, recruit, route to Auditor), `swarm/concurrency_cap.py` all in place. **Checkpoint:** Commander + Auditor + ReconScout together surface Juice Shop's SQLi endpoint; Auditor seals a 5-event chain; `verify` → "Chain OK".
- **Jun 17.** `tools/sqli_tools.py` (`run_sqlmap`), `agents/sqli_hunter.py` (capability check + approval gate), `agents/scope_warden.py` (`issue_capability`/`revoke`), kill-switch wired. Full 6-beat loop runs end-to-end and is timed. `scale_test/connect_harness.py` exercises 30 WS.
- **Jun 18.** README (diagram, GIF, install) + polish + full dry runs (auto-approve smoke, then human-in-loop) + scale screenshots done. *Augie: video recorded + slides final.* Buffer remaining.
- **Jun 19 AM.** Final record + submission form + link check + final commit landed by ~10:00 ET (1h buffer before 11:00).

**Stretch (only if ahead):** Elixir ScopeWarden hitting Band's REST Agent API (cross-runtime "three frameworks in one room" beat — reuses Josh's hardened Elixir directly); deeper specialist tools (`jwt_crack`, `idor_fuzz`, `run_dalfox`) now that SQLi/XSS/Auth specialists are built; `viewer/` live SSE case-viewer; 30→50-agent scale.

---

## Scale test (honest framing — never faked)

Live demo runs ~10–30 **real** Band agents. The "1000" headline = worker-job fan-out + a connect harness, stated plainly in the README:

| Test | Proves | Does NOT prove |
|---|---|---|
| `connect_harness --agents 30 --hold 60` | Band holds 30 persistent WS from one host | 30 ≠ 1000; server limits at scale unknown |
| `worker_fanout_bench --workers 200` | fan-out machinery + concurrency cap work | these are coroutines, not 200 WS agents |
| Architecture + README | design *could* reach 1000 by distributing workers | a design claim, not a live measurement |

README line: *"Worker layer scales toward 1000 concurrent tasks by distributing across machines; demonstrated here with 200-worker fan-out + 30 live Band agents. Full 1000-WS scale needs Band enterprise tier; the architecture is unchanged."*

---

## Risks + mitigations

1. **Band account quota (HIGHEST — surfaces tonight).** Unknown: cap on registered agents / simultaneous WS / msgs-per-min on hackathon tier. Mitigation: all agents registered + connected tonight; if capped near ~5, Reporter folds into Auditor and Auth into XSS; if WS cap ≤3, on-demand connect/disconnect redesign (~1 day). A Band-support email on hackathon limits goes out tonight.
2. **Token cost.** 6-agent multi-turn loop. Mitigation: governance logic stays in unit tests (no API); agents iterate on Haiku, Sonnet only for the final record. Full loop ≈ 20–30k tokens (~$0.50–1.00); dev ≈ $5–10.
3. **sqlmap slow/flaky on stage.** Mitigation: `--batch --level=1 --technique=U --time-sec=3`; fallback `manual_sqli_probe` with a known-good UNION payload (deterministic, <1s); a pre-recorded successful run kept as backup.
4. **WS instability on long sessions.** Mitigation: SDK auto-manages WS; demo is <30 min live; keepalive added in `connect_harness`.
5. **Recruit contact-relationship constraint.** Mitigation: one account = siblings (handled by design).
6. **`scope_guard` blocks itself.** Mitigation: `test_scope_guard.py` asserts `localhost:3000` passes and `google.com:443` blocks; `scoped_run` strips sqlmap `*` markers before host extraction; tests run before every demo.

---

## End-to-end verification

```bash
docker compose up -d juice-shop && curl -s localhost:3000 | grep -q OWASP && echo "Juice Shop OK"
uv run pytest tests/ -v                          # all green incl. tamper test (verify_chain -> False on mutation)
python -m agents.auditor --test-mode             # connects to Band, logs, writes chain, verifies
python -m swarm.launcher --smoke --auto-approve --engagement-id smoke-$(date +%s)   # mini loop seals + verifies
python -m swarm.launcher --engagement-id demo-01 # full 6-beat; human types 'approved'; sqlmap pops; bundle sealed
python -m governance.verify engagements/demo-01/demo-01_bundle.tar.gz   # "Chain OK — N events, no tampering"
python -m scale_test.worker_fanout_bench --workers 1000 --cap 16
python -m scale_test.connect_harness --hold 60
```

---

## Critical break-points (watch these 3)

1. **`agents/base_agent.py`** — Band SDK adapter + WS + `approval_gate` blocking on inbound @mention. If message delivery / @mention filtering differs from docs, the gate fails. Isolated trivial-agent test comes first (tonight/Jun 15) before anything builds on it.
2. **`governance/audit_ledger.py` + Auditor single-writer** — concurrent specialist @mentions may arrive out of room-order; chain stays valid but seq ≠ room order. Noted in README.
3. **`tools/_subprocess.py:scoped_run`** — sqlmap URL `*` markers can trip `scope_guard`; markers stripped / base host extracted before the check; dedicated test covers it.

---

## Inputs needed before execution

- Final name → repo name (recommend `leash`).
- Augie's GitHub username → collaborator (repo private during build → public before submission).
- Band quota answer (from tonight's registration) + `ANTHROPIC_API_KEY` in `.env`.

## Rollback

Greenfield repo — no existing system touched. Rollback = delete the repo / `git reset`. The Diogenes umbrella and the `feat/rsi-loop` branch are untouched by this work.
