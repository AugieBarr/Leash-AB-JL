"""viewer — live audit-stream viewer for a Leash engagement (zero dependencies).

Tails ``engagements/<id>/audit.ndjson`` over Server-Sent Events and renders the
governance story live: every event as it lands, the running chain-tail hash, the
event count, and a VERIFIED / TAMPERED badge re-derived on each append (the
public key is taken from the engagement's own key file, exactly as the offline
verifier does it).

This is the visible counterpart to ``python -m governance.verify`` — the same
tamper-evidence, shown streaming instead of as a one-shot CLI result.

Built on the standard library's ``http.server`` rather than FastAPI/uvicorn: a
read-only local SSE tail needs no framework, and zero extra deps keeps the demo
one ``python -m`` away with nothing to install. The UI follows the Roan Co.
design language (Geist + DM Serif Display, terracotta accent, grain, dash cards).

    python -m viewer.viewer                 # serve on http://localhost:8089
    python -m viewer.viewer --port 9000
    python -m viewer.viewer --engagement offline-demo
"""
from __future__ import annotations

import argparse
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from governance.audit_ledger import verify_ndjson

ROOT = Path(os.getenv("LEASH_ENGAGEMENTS", "engagements"))
POLL_SECONDS = 0.5


def _engagements() -> list[str]:
    if not ROOT.exists():
        return []
    return sorted(
        d.name for d in ROOT.iterdir() if d.is_dir() and (d / "audit.ndjson").exists()
    )


def _pubkey_for(engagement: str):
    """Derive the Ed25519 public key from the engagement's own key file.

    For a live (unsealed) engagement the private key sits beside the ledger on
    the operator's machine; the public half verifies every signature.
    """
    key_path = ROOT / engagement / "engagement_ed25519.key"
    if not key_path.exists():
        return None
    return Ed25519PrivateKey.from_private_bytes(key_path.read_bytes()).public_key()


def _read_lines(engagement: str) -> list[str]:
    path = ROOT / engagement / "audit.ndjson"
    if not path.exists():
        return []
    return [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _status(engagement: str, lines: list[str]) -> dict:
    """Verification badge + chain-tail for the current ledger state."""
    pk = _pubkey_for(engagement)
    path = ROOT / engagement / "audit.ndjson"
    if pk is None or not path.exists() or not lines:
        return {"ok": None, "detail": "waiting for first event…", "count": 0, "tail": ""}
    res = verify_ndjson(path, pk)
    tail = json.loads(lines[-1]).get("hash_prev", "")  # next event binds to the tail
    # The true tail is the last record's chain_hash; surface the last linkage hash
    # so the operator can eyeball the chain advancing. The verifier above is the
    # authority on integrity.
    return {"ok": res.ok, "detail": res.detail, "count": len(lines), "tail_b64": tail}


class _Handler(BaseHTTPRequestHandler):
    # Quiet the default per-request stderr logging; the demo narrates itself.
    def log_message(self, *args) -> None:  # noqa: D401
        return

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._serve_index()
        elif parsed.path == "/list":
            self._serve_json({"engagements": _engagements()})
        elif parsed.path == "/events":
            qs = parse_qs(parsed.query)
            engagement = (qs.get("engagement") or [""])[0]
            self._serve_stream(engagement)
        else:
            self.send_error(404)

    # ----- responses -----------------------------------------------------
    def _serve_json(self, obj: dict) -> None:
        body = json.dumps(obj).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_index(self) -> None:
        body = INDEX_HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_stream(self, engagement: str) -> None:
        if not engagement:
            self.send_error(400, "missing ?engagement=")
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        sent = 0
        last_status = None
        try:
            while True:
                lines = _read_lines(engagement)
                for raw in lines[sent:]:
                    self._sse("event", json.loads(raw))
                if len(lines) != sent:
                    sent = len(lines)
                    status = _status(engagement, lines)
                    self._sse("status", status)
                    last_status = status
                elif last_status is None:
                    last_status = _status(engagement, lines)
                    self._sse("status", last_status)
                self._sse("ping", {"t": sent})  # keep the socket warm; detects disconnect
                time.sleep(POLL_SECONDS)
        except (BrokenPipeError, ConnectionResetError):
            return  # client closed the tab — end the stream thread cleanly

    def _sse(self, event: str, data: dict) -> None:
        chunk = f"event: {event}\ndata: {json.dumps(data)}\n\n".encode("utf-8")
        self.wfile.write(chunk)
        self.wfile.flush()


INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Leash — Live Audit Stream</title>
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@300;400;500;600;700&family=Geist+Mono:wght@400;500&family=DM+Serif+Display&display=swap" rel="stylesheet" />
<style>
  :root {
    --bg: #0a0a0a; --bg-elevated: #141414; --text: #ededed; --text-muted: #888888;
    --accent: #E8735A; --accent-30: rgba(232,115,90,0.30); --accent-60: rgba(232,115,90,0.60);
    --border: rgba(255,255,255,0.06); --border-hover: rgba(232,115,90,0.30);
    --ok: #4cc2a8; --bad: #e5544c;
    --font-sans: 'Geist', ui-sans-serif, system-ui, -apple-system, sans-serif;
    --font-mono: 'Geist Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
    --font-serif: 'DM Serif Display', Georgia, serif;
    --radius: 8px;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html { scroll-behavior: smooth; }
  body {
    background: var(--bg); color: var(--text);
    font-family: var(--font-sans); font-size: 14px; line-height: 1.6;
    -webkit-font-smoothing: antialiased; overflow-x: hidden;
  }
  ::selection { background: var(--accent); color: var(--bg); }
  body::before {
    content: ""; position: fixed; inset: 0; z-index: 9999; pointer-events: none; opacity: 0.022;
    background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
    background-size: 256px 256px;
  }
  ::-webkit-scrollbar { width: 3px; }
  ::-webkit-scrollbar-track { background: var(--bg); }
  ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.08); border-radius: 2px; }
  ::-webkit-scrollbar-thumb:hover { background: var(--accent); }

  /* ---- sticky top bar (nav-blur) — pins the live status ---- */
  .topbar {
    position: sticky; top: 0; z-index: 50;
    display: flex; align-items: center; gap: 20px;
    padding: 16px clamp(20px, 5vw, 56px);
    background: rgba(10,10,10,0.82);
    backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
    border-bottom: 1px solid var(--border);
  }
  .brand { display: flex; align-items: baseline; gap: 9px; }
  .brand .mark { font-family: var(--font-serif); font-size: 21px; letter-spacing: -0.01em; color: var(--text); }
  .brand .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--accent); align-self: center; }
  .brand .rule { width: 1px; height: 16px; background: var(--border); margin: 0 4px; align-self: center; }
  .brand .sub { font-family: var(--font-mono); font-size: 10.5px; letter-spacing: 0.22em; text-transform: uppercase; color: var(--text-muted); }
  .stats { display: flex; align-items: center; gap: 18px; margin-left: auto; }
  .stat { display: flex; flex-direction: column; gap: 2px; }
  .stat .k { font-family: var(--font-mono); font-size: 9px; letter-spacing: 0.2em; text-transform: uppercase; color: var(--text-muted); }
  .stat .v { font-family: var(--font-mono); font-size: 13px; color: var(--text); }
  .stat .v.accent { color: var(--accent); }
  .badge {
    display: inline-flex; align-items: center; gap: 7px;
    font-size: 11px; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase;
    padding: 6px 12px; border-radius: 6px; border: 1px solid var(--border); color: var(--text-muted);
  }
  .badge .pulse { width: 6px; height: 6px; border-radius: 50%; background: currentColor; animation: pulse 1.8s ease-in-out infinite; }
  @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.35; } }
  .badge.ok { color: var(--ok); border-color: rgba(76,194,168,0.4); background: rgba(76,194,168,0.07); }
  .badge.bad { color: var(--bad); border-color: rgba(229,84,76,0.45); background: rgba(229,84,76,0.08); }
  select {
    appearance: none; background: var(--bg-elevated); color: var(--text);
    border: 1px solid var(--border); border-radius: 6px; padding: 7px 12px;
    font-family: var(--font-mono); font-size: 12px; cursor: pointer;
  }
  select:hover { border-color: var(--border-hover); }

  .wrap { max-width: 920px; margin: 0 auto; padding: 0 clamp(20px, 5vw, 56px) 96px; }

  /* ---- hero band ---- */
  .hero { padding: 56px 0 30px; }
  .eyebrow { display: flex; align-items: center; gap: 12px; margin-bottom: 18px; }
  .eyebrow .line { height: 1px; width: 32px; background: var(--accent); }
  .eyebrow .label { font-size: 10px; letter-spacing: 0.3em; text-transform: uppercase; color: var(--accent); font-weight: 500; }
  .eyebrow .num { font-family: var(--font-mono); color: var(--accent-30); margin-right: 8px; }
  .hero h1 { font-family: var(--font-serif); font-size: clamp(2.4rem, 6vw, 4.25rem); line-height: 0.95; letter-spacing: -0.02em; color: var(--text); }
  .hero .meta { margin-top: 16px; font-family: var(--font-mono); font-size: 12.5px; color: var(--text-muted); }
  .hero .meta b { color: var(--accent-60); font-weight: 500; }
  .hero .detail { margin-top: 6px; font-size: 13px; color: var(--text-muted); line-height: 1.7; max-width: 560px; }

  .sechead { display: flex; align-items: center; gap: 12px; margin: 8px 0 22px; }
  .sechead .line { height: 1px; width: 32px; background: var(--accent); }
  .sechead .label { font-size: 10px; letter-spacing: 0.3em; text-transform: uppercase; color: var(--accent); font-weight: 500; }
  .sechead .num { font-family: var(--font-mono); color: var(--accent-30); margin-right: 8px; }

  /* ---- event cards (Roan dash-card) ---- */
  #events { display: flex; flex-direction: column; gap: 12px; }
  .ev {
    position: relative; background: var(--bg-elevated);
    border: 1px solid var(--border); border-left: 2px solid var(--border);
    border-radius: var(--radius); padding: 20px 24px;
    transition: border-color .4s ease, transform .4s ease, box-shadow .4s ease;
    animation: rise .35s var(--ease, cubic-bezier(0.25,0.1,0.25,1));
  }
  @keyframes rise { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
  .ev:hover { border-color: var(--border-hover); transform: translateY(-4px); box-shadow: 0 24px 48px -12px rgba(232,115,90,0.06); }
  .ev.gate { border-left-color: var(--accent); }
  .ev.deny { border-left-color: var(--bad); }
  .ev.seal { border-left-color: var(--ok); }
  .ev .dash { height: 2px; width: 40px; border-radius: 999px; background: var(--accent-30); margin-bottom: 16px; transition: width .5s ease, background .5s ease; }
  .ev:hover .dash { width: 84px; background: var(--accent); }
  .ev-top { display: flex; align-items: baseline; gap: 12px; }
  .ev .seq { font-family: var(--font-mono); font-size: 12px; font-weight: 500; color: var(--accent-30); }
  .ev .kind { font-size: 14px; font-weight: 600; color: var(--text); transition: color .3s ease; letter-spacing: -0.005em; }
  .ev:hover .kind { color: var(--accent); }
  .ev .tag { margin-left: auto; font-family: var(--font-mono); font-size: 9.5px; letter-spacing: 0.16em; text-transform: uppercase; color: var(--text-muted); border: 1px solid var(--border); padding: 3px 8px; border-radius: 5px; }
  .ev .tag.gate { color: var(--accent); border-color: var(--accent-30); }
  .ev .tag.deny { color: var(--bad); border-color: rgba(229,84,76,0.4); }
  .ev .tag.seal { color: var(--ok); border-color: rgba(76,194,168,0.4); }
  .ev .pay { margin-top: 9px; font-size: 12.5px; color: var(--text-muted); line-height: 1.75; word-break: break-word; }
  .ev .pay key { font-family: var(--font-mono); color: var(--accent-60); }
  .ev .pay val { color: var(--text); }
  .ev .pay sep { color: var(--border); margin: 0 8px; }

  .empty { padding: 48px 0; text-align: center; color: var(--text-muted); font-family: var(--font-mono); font-size: 13px; }
  .accent-line { height: 1px; background: linear-gradient(90deg, transparent, var(--accent), transparent); opacity: 0.15; margin: 34px 0 18px; }
  footer { color: var(--text-muted); font-size: 12px; line-height: 1.8; }
  footer code { font-family: var(--font-mono); color: var(--accent); }
  footer .ro { display: block; margin-top: 4px; font-size: 11px; color: rgba(136,136,136,0.6); }

  @media (max-width: 720px) {
    .stats .stat.tail { display: none; }
    .ev:hover { transform: none; box-shadow: none; }
  }
</style>
</head>
<body>
  <div class="topbar">
    <div class="brand">
      <span class="mark">Leash</span><span class="dot"></span>
      <span class="rule"></span>
      <span class="sub">Audit Stream</span>
    </div>
    <div class="stats">
      <span id="badge" class="badge"><span class="pulse"></span> connecting</span>
      <div class="stat"><span class="k">Events</span><span id="count" class="v accent">0</span></div>
      <div class="stat tail"><span class="k">Chain Tail</span><span id="tail" class="v">—</span></div>
      <select id="pick" title="engagement"></select>
    </div>
  </div>

  <div class="wrap">
    <div class="hero">
      <div class="eyebrow"><span class="line"></span><span class="label"><span class="num">01</span>Live Engagement</span></div>
      <h1 id="eng-name">—</h1>
      <div class="meta">target <b id="eng-target">—</b></div>
      <div class="detail">Every agent action is bound into a tamper-evident, Ed25519-signed audit chain and re-verified the instant it lands. This is the visible twin of <code>python -m governance.verify</code>.</div>
    </div>

    <div class="sechead"><span class="line"></span><span class="label"><span class="num">02</span>Audit Chain</span></div>
    <div id="events"><div class="empty">waiting for the first event…</div></div>

    <div class="accent-line"></div>
    <footer>
      Verify the sealed bundle offline: <code>python -m governance.verify &lt;bundle.tar.gz&gt;</code>
      <span class="ro">Read-only viewer · the ledger is never written here, only verified.</span>
    </footer>
  </div>

<script>
  const $ = (id) => document.getElementById(id);
  let es = null;

  function qsEngagement() {
    return new URLSearchParams(location.search).get("engagement") || "";
  }

  const KIND_CLASS = {
    approval: "gate", capability_issued: "gate", capability_check: "gate",
    scope_violation: "deny", blocked_halted: "deny", kill_switch: "deny", error: "deny",
    report_rendered: "seal", bundle_sealed: "seal", engagement_close: "seal",
  };
  const TAG_TEXT = {
    approval: "human gate", capability_issued: "scope", capability_check: "scope",
    blocked_halted: "kill-switch", kill_switch: "kill-switch", scope_violation: "blocked",
    error: "blocked", report_rendered: "report", bundle_sealed: "sealed",
  };

  function escapeHtml(s) {
    return String(s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
  }

  function renderPayload(payloadStr) {
    let obj;
    try { obj = JSON.parse(payloadStr); } catch { return escapeHtml(payloadStr); }
    return Object.entries(obj).map(([k, v]) => {
      let val;
      if (Array.isArray(v)) val = "[" + v.length + " item" + (v.length === 1 ? "" : "s") + "]";
      else if (v && typeof v === "object") val = "{…}";
      else val = String(v);
      return "<key>" + escapeHtml(k) + "</key> <val>" + escapeHtml(val) + "</val>";
    }).join('<sep>·</sep>');
  }

  function addEvent(rec) {
    const list = $("events");
    const empty = list.querySelector(".empty");
    if (empty) empty.remove();
    const cls = KIND_CLASS[rec.kind] || "";
    if (rec.kind === "engagement_open") {
      try { const p = JSON.parse(rec.payload); if (p.target) $("eng-target").textContent = p.target; } catch {}
    }
    const tag = TAG_TEXT[rec.kind];
    const div = document.createElement("div");
    div.className = "ev " + cls;
    div.innerHTML =
      '<div class="dash"></div>' +
      '<div class="ev-top">' +
        '<span class="seq">#' + rec.seq + '</span>' +
        '<span class="kind">' + escapeHtml(rec.kind) + '</span>' +
        (tag ? '<span class="tag ' + cls + '">' + tag + '</span>' : '') +
      '</div>' +
      '<div class="pay">' + renderPayload(rec.payload) + '</div>';
    list.appendChild(div);
    div.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }

  function setStatus(s) {
    $("count").textContent = s.count ?? 0;
    const badge = $("badge");
    if (s.ok === true) { badge.className = "badge ok"; badge.innerHTML = '<span class="pulse"></span> verified'; }
    else if (s.ok === false) { badge.className = "badge bad"; badge.innerHTML = '<span class="pulse"></span> tampered'; }
    else { badge.className = "badge"; badge.innerHTML = '<span class="pulse"></span> waiting'; }
    if (s.tail_b64) $("tail").textContent = s.tail_b64.replace(/=+$/, "").slice(0, 12) + "…";
  }

  function connect(engagement) {
    if (es) es.close();
    $("eng-name").textContent = engagement;
    $("eng-target").textContent = "—";
    $("events").innerHTML = '<div class="empty">waiting for the first event…</div>';
    es = new EventSource("/events?engagement=" + encodeURIComponent(engagement));
    es.addEventListener("event", (e) => addEvent(JSON.parse(e.data)));
    es.addEventListener("status", (e) => setStatus(JSON.parse(e.data)));
    es.onerror = () => { const b = $("badge"); b.className = "badge"; b.innerHTML = '<span class="pulse"></span> reconnecting'; };
  }

  async function init() {
    const res = await fetch("/list");
    const { engagements } = await res.json();
    const pick = $("pick");
    pick.innerHTML = "";
    for (const name of engagements) {
      const opt = document.createElement("option");
      opt.value = name; opt.textContent = name;
      pick.appendChild(opt);
    }
    let current = qsEngagement() || engagements[0] || "";
    if (current) pick.value = current;
    pick.onchange = () => {
      const v = pick.value;
      history.replaceState(null, "", "?engagement=" + encodeURIComponent(v));
      connect(v);
    };
    if (current) connect(current);
    else { $("events").innerHTML = '<div class="empty">no engagements found under engagements/</div>'; $("eng-name").textContent = "no engagement"; }
  }

  init();
</script>
</body>
</html>"""


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Live audit-stream viewer for a Leash engagement.")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=int(os.getenv("LEASH_VIEWER_PORT", "8089")))
    p.add_argument("--engagement", default=None, help="Open straight to this engagement.")
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    try:
        server = ThreadingHTTPServer((args.host, args.port), _Handler)
    except OSError as e:
        raise SystemExit(
            f"Could not bind {args.host}:{args.port} ({e.strerror or e}). "
            f"Another viewer may be running — stop it or pass --port <N>."
        )
    server.daemon_threads = True
    found = _engagements()
    suffix = f"?engagement={args.engagement}" if args.engagement else ""
    print(f"Leash viewer → http://{args.host}:{args.port}/{suffix}")
    print(f"  engagements: {', '.join(found) if found else '(none yet under ' + str(ROOT) + ')'}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nviewer stopped")
        server.shutdown()


if __name__ == "__main__":
    main()
