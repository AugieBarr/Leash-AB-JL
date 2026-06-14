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
one ``python -m`` away with nothing to install.

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
<style>
  :root {
    --bg: #0d0d0f; --panel: #141417; --line: #232327; --ink: #e8e8ea;
    --muted: #8a8a92; --accent: #d8a24a; --ok: #3fa66a; --bad: #cf4f4f;
    --radius: 8px;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--bg); color: var(--ink);
    font: 14px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  }
  .wrap { max-width: 860px; margin: 0 auto; padding: 28px 20px 80px; }
  header { display: flex; align-items: center; gap: 12px; margin-bottom: 6px; }
  h1 { font-size: 18px; font-weight: 650; margin: 0; letter-spacing: -0.01em; }
  .sub { color: var(--muted); font-size: 13px; margin: 0 0 22px; }
  .bar {
    display: flex; flex-wrap: wrap; align-items: center; gap: 14px;
    background: var(--panel); border: 1px solid var(--line);
    border-radius: var(--radius); padding: 14px 16px; margin-bottom: 18px;
  }
  .badge {
    font-weight: 650; font-size: 12px; letter-spacing: 0.04em; text-transform: uppercase;
    padding: 5px 10px; border-radius: 6px; border: 1px solid var(--line); color: var(--muted);
  }
  .badge.ok { color: var(--ok); border-color: rgba(63,166,106,0.5); }
  .badge.bad { color: var(--bad); border-color: rgba(207,79,79,0.5); }
  .meta { color: var(--muted); font-size: 12.5px; }
  .meta b { color: var(--ink); font-weight: 600; }
  .mono { font-family: ui-monospace, "SF Mono", Menlo, monospace; }
  select {
    margin-left: auto; background: var(--bg); color: var(--ink);
    border: 1px solid var(--line); border-radius: 6px; padding: 6px 8px; font-size: 13px;
  }
  #events { display: flex; flex-direction: column; gap: 8px; }
  .ev {
    background: var(--panel); border: 1px solid var(--line); border-left: 2px solid var(--line);
    border-radius: var(--radius); padding: 10px 14px; animation: in 0.25s ease;
  }
  @keyframes in { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; } }
  .ev.gate { border-left-color: var(--accent); }
  .ev.deny { border-left-color: var(--bad); }
  .ev.seal { border-left-color: var(--ok); }
  .ev-top { display: flex; align-items: baseline; gap: 10px; }
  .seq { font-family: ui-monospace, monospace; color: var(--accent); font-weight: 650; font-size: 12px; }
  .kind { font-weight: 600; font-size: 13px; }
  .pay { color: var(--muted); font-size: 12.5px; margin-top: 4px; word-break: break-word; }
  .pay code { color: var(--ink); }
  footer { color: var(--muted); font-size: 12px; margin-top: 26px; border-top: 1px solid var(--line); padding-top: 14px; }
  footer code { color: var(--accent); }
  .empty { color: var(--muted); padding: 30px 0; text-align: center; }
</style>
</head>
<body>
<div class="wrap">
  <header><h1>🐕‍🦺 Leash — Live Audit Stream</h1></header>
  <p class="sub">Tamper-evident engagement ledger, streaming and re-verified on every append.</p>

  <div class="bar">
    <span id="badge" class="badge">connecting…</span>
    <span class="meta">events <b id="count">0</b></span>
    <span class="meta">chain tail <b id="tail" class="mono">—</b></span>
    <select id="pick" title="engagement"></select>
  </div>

  <div id="events"><div class="empty">waiting for the first event…</div></div>

  <footer>Verify the sealed bundle offline: <code>python -m governance.verify &lt;bundle.tar.gz&gt;</code></footer>
</div>

<script>
  const $ = (id) => document.getElementById(id);
  let es = null;

  function qsEngagement() {
    return new URLSearchParams(location.search).get("engagement") || "";
  }

  const KIND_CLASS = {
    approval: "gate", scope_issue: "gate", capability: "gate",
    scope_violation: "deny", denied: "deny", blocked: "deny",
    seal: "seal", bundle_sealed: "seal", engagement_close: "seal",
  };

  function renderPayload(payloadStr) {
    let obj;
    try { obj = JSON.parse(payloadStr); } catch { return payloadStr; }
    return Object.entries(obj).map(([k, v]) => {
      let val;
      if (Array.isArray(v)) val = "[" + v.length + " item" + (v.length === 1 ? "" : "s") + "]";
      else if (v && typeof v === "object") val = "{…}";
      else val = String(v);
      return '<code>' + k + '</code>=' + escapeHtml(val);
    }).join("  ·  ");
  }

  function escapeHtml(s) {
    return s.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
  }

  function addEvent(rec) {
    const list = $("events");
    const empty = list.querySelector(".empty");
    if (empty) empty.remove();
    const div = document.createElement("div");
    div.className = "ev " + (KIND_CLASS[rec.kind] || "");
    div.innerHTML =
      '<div class="ev-top"><span class="seq">#' + rec.seq + '</span>' +
      '<span class="kind">' + escapeHtml(rec.kind) + '</span></div>' +
      '<div class="pay">' + renderPayload(rec.payload) + '</div>';
    list.appendChild(div);
    window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
  }

  function setStatus(s) {
    $("count").textContent = s.count ?? 0;
    const badge = $("badge");
    if (s.ok === true) { badge.className = "badge ok"; badge.textContent = "✓ verified"; }
    else if (s.ok === false) { badge.className = "badge bad"; badge.textContent = "✗ tampered"; }
    else { badge.className = "badge"; badge.textContent = "waiting…"; }
    if (s.tail_b64) {
      // show a short, stable fingerprint of the linkage hash
      $("tail").textContent = s.tail_b64.replace(/=+$/, "").slice(0, 12) + "…";
    }
  }

  function connect(engagement) {
    if (es) es.close();
    $("events").innerHTML = '<div class="empty">waiting for the first event…</div>';
    es = new EventSource("/events?engagement=" + encodeURIComponent(engagement));
    es.addEventListener("event", (e) => addEvent(JSON.parse(e.data)));
    es.addEventListener("status", (e) => setStatus(JSON.parse(e.data)));
    es.onerror = () => { $("badge").textContent = "reconnecting…"; $("badge").className = "badge"; };
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
    else $("events").innerHTML = '<div class="empty">no engagements found under engagements/</div>';
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
    server = ThreadingHTTPServer((args.host, args.port), _Handler)
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
