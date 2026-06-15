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
design language (Geist + DM Serif Display, terracotta accent, grain, dash cards)
and adds a live hash-chain spine, expandable events, kind filtering, search,
keyboard navigation, copy-to-clipboard, and tamper highlighting.

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
    # res.tail_hash is the true chain tail (hash of the last event); show a prefix so
    # the operator can watch the chain advance. verify_ndjson above is the integrity authority.
    return {"ok": res.ok, "detail": res.detail, "count": len(lines), "tail": res.tail_hash}


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
    --bg: #0a0a0a; --bg-elevated: #141414; --bg-2: #101010; --text: #ededed; --text-muted: #888888;
    --accent: #E8735A; --accent-30: rgba(232,115,90,0.30); --accent-60: rgba(232,115,90,0.60);
    --accent-08: rgba(232,115,90,0.08); --border: rgba(255,255,255,0.06); --border-hover: rgba(232,115,90,0.30);
    --ok: #4cc2a8; --ok-30: rgba(76,194,168,0.3); --bad: #e5544c; --bad-30: rgba(229,84,76,0.3);
    --font-sans: 'Geist', ui-sans-serif, system-ui, -apple-system, sans-serif;
    --font-mono: 'Geist Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
    --font-serif: 'DM Serif Display', Georgia, serif;
    --radius: 8px; --ease: cubic-bezier(0.25,0.1,0.25,1);
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html { scroll-behavior: smooth; }
  body { background: var(--bg); color: var(--text); font-family: var(--font-sans); font-size: 14px;
    line-height: 1.6; -webkit-font-smoothing: antialiased; overflow-x: hidden; }
  ::selection { background: var(--accent); color: var(--bg); }
  body::before { content: ""; position: fixed; inset: 0; z-index: 9999; pointer-events: none; opacity: 0.022;
    background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
    background-size: 256px 256px; }
  ::-webkit-scrollbar { width: 3px; height: 3px; }
  ::-webkit-scrollbar-track { background: var(--bg); }
  ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.08); border-radius: 2px; }
  ::-webkit-scrollbar-thumb:hover { background: var(--accent); }

  /* top bar */
  .topbar { position: sticky; top: 0; z-index: 50; display: flex; align-items: center; gap: 18px;
    padding: 14px clamp(18px, 5vw, 56px); background: rgba(10,10,10,0.82);
    backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px); border-bottom: 1px solid var(--border); }
  .brand { display: flex; align-items: baseline; gap: 9px; }
  .brand .mark { font-family: var(--font-serif); font-size: 21px; letter-spacing: -0.01em; }
  .brand .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--accent); align-self: center; }
  .brand .rule { width: 1px; height: 16px; background: var(--border); margin: 0 4px; align-self: center; }
  .brand .sub { font-family: var(--font-mono); font-size: 10.5px; letter-spacing: 0.22em; text-transform: uppercase; color: var(--text-muted); }
  .stats { display: flex; align-items: center; gap: 16px; margin-left: auto; }
  .stat { display: flex; flex-direction: column; gap: 1px; }
  .stat .k { font-family: var(--font-mono); font-size: 9px; letter-spacing: 0.2em; text-transform: uppercase; color: var(--text-muted); }
  .stat .v { font-family: var(--font-mono); font-size: 13px; color: var(--text); }
  .stat .v.accent { color: var(--accent); }
  .copyable { cursor: pointer; transition: color .2s ease; }
  .copyable:hover { color: var(--accent); }
  .copyable.flash { color: var(--ok) !important; }
  .badge { display: inline-flex; align-items: center; gap: 7px; font-size: 11px; font-weight: 600;
    letter-spacing: 0.08em; text-transform: uppercase; padding: 6px 12px; border-radius: 6px;
    border: 1px solid var(--border); color: var(--text-muted); white-space: nowrap; }
  .badge .pulse { width: 6px; height: 6px; border-radius: 50%; background: currentColor; animation: pulse 1.8s ease-in-out infinite; }
  @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.35; } }
  .badge.ok { color: var(--ok); border-color: var(--ok-30); background: rgba(76,194,168,0.07); }
  .badge.bad { color: var(--bad); border-color: var(--bad-30); background: rgba(229,84,76,0.08); }
  .iconbtn { display: inline-flex; align-items: center; justify-content: center; gap: 6px; height: 30px;
    padding: 0 11px; border: 1px solid var(--border); border-radius: 6px; background: var(--bg-elevated);
    color: var(--text-muted); font-family: var(--font-mono); font-size: 11px; cursor: pointer;
    transition: border-color .25s ease, color .25s ease; }
  .iconbtn:hover { border-color: var(--border-hover); color: var(--text); }
  .iconbtn.on { color: var(--accent); border-color: var(--accent-30); }
  select { appearance: none; background: var(--bg-elevated); color: var(--text); border: 1px solid var(--border);
    border-radius: 6px; padding: 7px 12px; font-family: var(--font-mono); font-size: 12px; cursor: pointer; }
  select:hover { border-color: var(--border-hover); }

  .wrap { max-width: 940px; margin: 0 auto; padding: 0 clamp(18px, 5vw, 56px) 110px; }

  /* hero */
  .hero { padding: 52px 0 26px; }
  .eyebrow { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
  .eyebrow .line { height: 1px; width: 32px; background: var(--accent); }
  .eyebrow .label { font-size: 10px; letter-spacing: 0.3em; text-transform: uppercase; color: var(--accent); font-weight: 500; }
  .eyebrow .num { font-family: var(--font-mono); color: var(--accent-30); margin-right: 8px; }
  .hero h1 { font-family: var(--font-serif); font-size: clamp(2.3rem, 6vw, 4.1rem); line-height: 0.95; letter-spacing: -0.02em; }
  .hero .meta { margin-top: 14px; font-family: var(--font-mono); font-size: 12.5px; color: var(--text-muted); }
  .hero .meta b { color: var(--accent-60); font-weight: 500; }
  .hero .detail { margin-top: 6px; font-size: 13px; color: var(--text-muted); line-height: 1.7; max-width: 560px; }

  .sechead { display: flex; align-items: center; gap: 12px; margin: 6px 0 18px; }
  .sechead .line { height: 1px; width: 32px; background: var(--accent); }
  .sechead .label { font-size: 10px; letter-spacing: 0.3em; text-transform: uppercase; color: var(--accent); font-weight: 500; }
  .sechead .num { font-family: var(--font-mono); color: var(--accent-30); margin-right: 8px; }

  /* control bar */
  .controls { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; margin-bottom: 20px; }
  .chips { display: flex; flex-wrap: wrap; gap: 7px; }
  .chip { font-family: var(--font-mono); font-size: 10.5px; letter-spacing: 0.04em; padding: 5px 10px;
    border: 1px solid var(--border); border-radius: 999px; color: var(--text-muted); cursor: pointer;
    transition: all .2s ease; user-select: none; white-space: nowrap; }
  .chip:hover { border-color: var(--border-hover); color: var(--text); }
  .chip.on { color: var(--accent); border-color: var(--accent-30); background: var(--accent-08); }
  .chip .c { color: var(--accent-30); margin-left: 5px; }
  .chip.on .c { color: var(--accent-60); }
  .search { margin-left: auto; display: flex; align-items: center; gap: 8px; background: var(--bg-elevated);
    border: 1px solid var(--border); border-radius: 6px; padding: 0 11px; height: 32px; min-width: 200px;
    transition: border-color .25s ease; }
  .search:focus-within { border-color: var(--border-hover); }
  .search svg { color: var(--text-muted); flex-shrink: 0; }
  .search input { background: transparent; border: none; outline: none; color: var(--text);
    font-family: var(--font-mono); font-size: 12px; width: 100%; }
  .search input::placeholder { color: var(--text-muted); }
  .showing { font-family: var(--font-mono); font-size: 10.5px; color: var(--text-muted); white-space: nowrap; }

  /* chain stream + spine */
  #stream { position: relative; }
  .ev-row { display: flex; gap: 16px; position: relative; padding-bottom: 12px; }
  .ev-row:last-child { padding-bottom: 0; }
  .rail { width: 14px; flex-shrink: 0; display: flex; justify-content: center; position: relative; }
  .rail::before { content: ""; position: absolute; top: 26px; bottom: -2px; width: 2px;
    background: linear-gradient(var(--accent-30), var(--border)); }
  .ev-row:last-child .rail::before { display: none; }
  .node { width: 11px; height: 11px; border-radius: 50%; background: var(--bg); border: 2px solid var(--accent);
    margin-top: 20px; z-index: 1; transition: transform .25s ease, border-color .25s ease, background .25s ease; }
  .ev-row.open .node, .ev-row.focus .node { transform: scale(1.35); background: var(--accent); }
  .ev-row.bad .node { border-color: var(--bad); background: var(--bad); }

  .ev { flex: 1; min-width: 0; background: var(--bg-elevated); border: 1px solid var(--border);
    border-left: 2px solid var(--border); border-radius: var(--radius); padding: 16px 20px; cursor: pointer;
    transition: border-color .3s ease, transform .3s ease, box-shadow .3s ease; animation: rise .35s var(--ease); }
  @keyframes rise { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
  .ev:hover { border-color: var(--border-hover); transform: translateY(-2px); box-shadow: 0 18px 40px -16px rgba(232,115,90,0.10); }
  .ev-row.focus .ev { border-color: var(--accent-30); box-shadow: 0 0 0 1px var(--accent-30); }
  .ev-row.gate .ev { border-left-color: var(--accent); }
  .ev-row.deny .ev, .ev-row.bad .ev { border-left-color: var(--bad); }
  .ev-row.seal .ev { border-left-color: var(--ok); }
  .ev .dash { height: 2px; width: 38px; border-radius: 999px; background: var(--accent-30); margin-bottom: 13px; transition: width .5s ease, background .5s ease; }
  .ev:hover .dash, .ev-row.open .ev .dash { width: 80px; background: var(--accent); }
  .ev-top { display: flex; align-items: baseline; gap: 11px; }
  .ev .seq { font-family: var(--font-mono); font-size: 12px; font-weight: 500; color: var(--accent-30); }
  .ev .kind { font-size: 14px; font-weight: 600; transition: color .3s ease; letter-spacing: -0.005em; }
  .ev:hover .kind, .ev-row.open .ev .kind { color: var(--accent); }
  .ev-row.bad .ev .kind { color: var(--bad); }
  .ev .tag { font-family: var(--font-mono); font-size: 9.5px; letter-spacing: 0.16em; text-transform: uppercase;
    color: var(--text-muted); border: 1px solid var(--border); padding: 3px 8px; border-radius: 5px; }
  .ev .tag.gate { color: var(--accent); border-color: var(--accent-30); }
  .ev .tag.deny { color: var(--bad); border-color: var(--bad-30); }
  .ev .tag.seal { color: var(--ok); border-color: var(--ok-30); }
  .ev .chev { margin-left: auto; color: var(--text-muted); transition: transform .3s ease, color .2s ease; flex-shrink: 0; }
  .ev:hover .chev { color: var(--accent); }
  .ev-row.open .chev { transform: rotate(180deg); }
  .ev .pay { margin-top: 8px; font-size: 12.5px; color: var(--text-muted); line-height: 1.7; word-break: break-word;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .ev .pay key { font-family: var(--font-mono); color: var(--accent-60); }
  .ev .pay sep { color: var(--border); margin: 0 7px; }

  /* expandable detail */
  .detail-wrap { display: grid; grid-template-rows: 0fr; transition: grid-template-rows .35s var(--ease); }
  .ev-row.open .detail-wrap { grid-template-rows: 1fr; }
  .detail-inner { overflow: hidden; }
  .detail { margin-top: 14px; padding-top: 14px; border-top: 1px solid var(--border); }
  .detail pre { font-family: var(--font-mono); font-size: 11.5px; line-height: 1.65; color: var(--text);
    background: var(--bg-2); border: 1px solid var(--border); border-radius: 6px; padding: 12px 14px;
    overflow-x: auto; white-space: pre; }
  .kv { display: flex; gap: 10px; margin-top: 10px; font-family: var(--font-mono); font-size: 10.5px; align-items: baseline; }
  .kv .lab { color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.14em; min-width: 76px; flex-shrink: 0; }
  .kv .val { color: var(--text); word-break: break-all; }
  .link-prev { margin-top: 12px; font-family: var(--font-mono); font-size: 10.5px; color: var(--accent-60);
    display: flex; align-items: center; gap: 7px; }
  .link-prev .arrow { color: var(--accent); }

  .empty { padding: 48px 0; text-align: center; color: var(--text-muted); font-family: var(--font-mono); font-size: 13px; }
  .accent-line { height: 1px; background: linear-gradient(90deg, transparent, var(--accent), transparent); opacity: 0.15; margin: 30px 0 16px; }
  footer { color: var(--text-muted); font-size: 12px; line-height: 1.8; }
  footer code { font-family: var(--font-mono); color: var(--accent); }
  footer .ro { display: block; margin-top: 3px; font-size: 11px; color: rgba(136,136,136,0.6); }

  /* shortcuts overlay */
  .overlay { position: fixed; inset: 0; z-index: 200; background: rgba(8,8,8,0.72);
    backdrop-filter: blur(4px); -webkit-backdrop-filter: blur(4px); display: none; align-items: center; justify-content: center; }
  .overlay.show { display: flex; animation: fade .2s ease; }
  @keyframes fade { from { opacity: 0; } to { opacity: 1; } }
  .sheet { background: var(--bg-elevated); border: 1px solid var(--border); border-radius: 10px; padding: 26px 30px;
    width: min(420px, 90vw); }
  .sheet h3 { font-family: var(--font-serif); font-size: 22px; margin-bottom: 4px; }
  .sheet p { color: var(--text-muted); font-size: 12.5px; margin-bottom: 18px; }
  .keyrow { display: flex; justify-content: space-between; align-items: center; padding: 8px 0; border-top: 1px solid var(--border); }
  .keyrow span { color: var(--text-muted); font-size: 13px; }
  .keyrow kbd { font-family: var(--font-mono); font-size: 11px; color: var(--text); background: var(--bg-2);
    border: 1px solid var(--border); border-radius: 5px; padding: 3px 8px; }
  .toast { position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%) translateY(20px);
    background: var(--bg-elevated); border: 1px solid var(--accent-30); border-radius: 8px; padding: 10px 16px;
    font-family: var(--font-mono); font-size: 12px; color: var(--text); opacity: 0; pointer-events: none;
    transition: opacity .25s ease, transform .25s ease; z-index: 300; }
  .toast.show { opacity: 1; transform: translateX(-50%) translateY(0); }

  @media (max-width: 760px) {
    .stat.tailstat { display: none; }
    .search { min-width: 140px; }
    .ev:hover { transform: none; box-shadow: none; }
  }
</style>
</head>
<body>
  <div class="topbar">
    <div class="brand"><span class="mark">Leash</span><span class="dot"></span><span class="rule"></span><span class="sub">Audit Stream</span></div>
    <div class="stats">
      <span id="badge" class="badge"><span class="pulse"></span> connecting</span>
      <div class="stat"><span class="k">Events</span><span id="count" class="v accent">0</span></div>
      <div class="stat tailstat"><span class="k">Chain Tail</span><span id="tail" class="v copyable" title="click to copy full hash">—</span></div>
      <button id="follow" class="iconbtn on" title="auto-follow new events">● live</button>
      <button id="help" class="iconbtn" title="keyboard shortcuts">?</button>
      <select id="pick" title="engagement"></select>
    </div>
  </div>

  <div class="wrap">
    <div class="hero">
      <div class="eyebrow"><span class="line"></span><span class="label"><span class="num">01</span>Live Engagement</span></div>
      <h1 id="eng-name">—</h1>
      <div class="meta">target <b id="eng-target">—</b></div>
      <div class="detail">Every agent action is bound into a tamper-evident, Ed25519-signed hash chain and re-verified the instant it lands. Click any event to inspect its payload, signature, and chain link. This is the visible twin of <code>python -m governance.verify</code>.</div>
    </div>

    <div class="sechead"><span class="line"></span><span class="label"><span class="num">02</span>Audit Chain</span></div>

    <div class="controls">
      <div id="chips" class="chips"></div>
      <div class="search">
        <svg width="13" height="13" viewBox="0 0 16 16" fill="none"><circle cx="7" cy="7" r="5" stroke="currentColor" stroke-width="1.5"/><path d="M11 11l3 3" stroke="currentColor" stroke-width="1.5"/></svg>
        <input id="q" placeholder="search payloads…  ( / )" spellcheck="false" />
      </div>
      <span id="showing" class="showing"></span>
    </div>

    <div id="stream"><div class="empty">waiting for the first event…</div></div>

    <div class="accent-line"></div>
    <footer>
      Verify the sealed bundle offline: <code>python -m governance.verify &lt;bundle.tar.gz&gt;</code>
      <span class="ro">Read-only viewer · the ledger is never written here, only verified.</span>
    </footer>
  </div>

  <div id="overlay" class="overlay"><div class="sheet">
    <h3>Shortcuts</h3><p>Navigate the chain without leaving the keyboard.</p>
    <div class="keyrow"><span>Next / previous event</span><kbd>j</kbd></div>
    <div class="keyrow"><span>Expand / collapse focused</span><kbd>enter</kbd></div>
    <div class="keyrow"><span>Focus search</span><kbd>/</kbd></div>
    <div class="keyrow"><span>Collapse all · clear search</span><kbd>esc</kbd></div>
    <div class="keyrow"><span>Toggle live follow</span><kbd>f</kbd></div>
    <div class="keyrow"><span>This help</span><kbd>?</kbd></div>
  </div></div>
  <div id="toast" class="toast"></div>

<script>
  const $ = (id) => document.getElementById(id);
  const stream = $("stream");
  let es = null, events = [], rows = [], kinds = new Map(), activeKinds = new Set();
  let query = "", follow = true, focusIdx = -1, badSeq = null;

  function qsEngagement() { return new URLSearchParams(location.search).get("engagement") || ""; }
  const esc = (s) => String(s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));

  const KIND_CLASS = { approval: "gate", capability_issued: "gate", capability_check: "gate",
    scope_violation: "deny", blocked_halted: "deny", kill_switch: "deny", error: "deny",
    report_rendered: "seal", bundle_sealed: "seal", engagement_close: "seal" };
  const TAG_TEXT = { approval: "human gate", capability_issued: "scope", capability_check: "scope",
    blocked_halted: "kill-switch", kill_switch: "kill-switch", scope_violation: "blocked", error: "blocked",
    report_rendered: "report", bundle_sealed: "sealed", engagement_close: "closed" };

  function summarize(payloadStr) {
    let obj; try { obj = JSON.parse(payloadStr); } catch { return esc(payloadStr); }
    return Object.entries(obj).map(([k, v]) => {
      let val = Array.isArray(v) ? "[" + v.length + " item" + (v.length === 1 ? "" : "s") + "]"
        : (v && typeof v === "object") ? "{…}" : String(v);
      return "<key>" + esc(k) + "</key> " + esc(val);
    }).join('<sep>·</sep>');
  }
  function pretty(payloadStr) { try { return esc(JSON.stringify(JSON.parse(payloadStr), null, 2)); } catch { return esc(payloadStr); } }

  function toast(msg) { const t = $("toast"); t.textContent = msg; t.classList.add("show"); clearTimeout(t._t); t._t = setTimeout(() => t.classList.remove("show"), 1400); }
  function copy(text, el) {
    navigator.clipboard.writeText(text).then(() => {
      toast("copied to clipboard");
      if (el) { el.classList.add("flash"); setTimeout(() => el.classList.remove("flash"), 600); }
    }).catch(() => toast("copy failed"));
  }

  function addEvent(rec) {
    const empty = stream.querySelector(".empty"); if (empty) empty.remove();
    events.push(rec);
    kinds.set(rec.kind, (kinds.get(rec.kind) || 0) + 1);
    if (rec.kind === "engagement_open") { try { const p = JSON.parse(rec.payload); if (p.target) $("eng-target").textContent = p.target; } catch {} }

    const cls = KIND_CLASS[rec.kind] || "", tag = TAG_TEXT[rec.kind];
    const row = document.createElement("div");
    row.className = "ev-row " + cls;
    row.dataset.seq = rec.seq; row.dataset.kind = rec.kind;
    row.dataset.text = (rec.kind + " " + rec.payload).toLowerCase();
    row.innerHTML =
      '<div class="rail"><div class="node"></div></div>' +
      '<div class="ev">' +
        '<div class="dash"></div>' +
        '<div class="ev-top">' +
          '<span class="seq">#' + rec.seq + '</span>' +
          '<span class="kind">' + esc(rec.kind) + '</span>' +
          (tag ? '<span class="tag ' + cls + '">' + tag + '</span>' : '') +
          '<svg class="chev" width="13" height="13" viewBox="0 0 16 16" fill="none"><path d="M4 6l4 4 4-4" stroke="currentColor" stroke-width="1.5"/></svg>' +
        '</div>' +
        '<div class="pay">' + summarize(rec.payload) + '</div>' +
        '<div class="detail-wrap"><div class="detail-inner"><div class="detail">' +
          '<pre>' + pretty(rec.payload) + '</pre>' +
          '<div class="kv"><span class="lab">hash_prev</span><span class="val copyable" data-copy="' + esc(rec.hash_prev || "") + '">' + esc((rec.hash_prev || "").slice(0, 44)) + '…</span></div>' +
          '<div class="kv"><span class="lab">signature</span><span class="val copyable" data-copy="' + esc(rec.sig || "") + '">' + esc((rec.sig || "").slice(0, 44)) + '…</span></div>' +
          (rec.seq > 0 ? '<div class="link-prev"><span class="arrow">↑</span> hash_prev binds this event to <b>#' + (rec.seq - 1) + '</b> — break any earlier event and every link below fails.</div>'
                       : '<div class="link-prev"><span class="arrow">⚓</span> genesis — hash_prev is 32 zero bytes.</div>') +
        '</div></div></div>' +
      '</div>';
    stream.appendChild(row);
    rows.push(row);

    const ev = row.querySelector(".ev");
    ev.addEventListener("click", (e) => { if (e.target.closest(".copyable")) return; toggle(row); });
    row.querySelectorAll(".copyable").forEach((c) => c.addEventListener("click", (e) => { e.stopPropagation(); copy(c.dataset.copy, c); }));

    applyFilters();
    renderChips();
    if (follow) row.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }

  function toggle(row) { row.classList.toggle("open"); }

  function renderChips() {
    const chips = $("chips");
    const entries = [["all", events.length], ...[...kinds.entries()].sort((a, b) => b[1] - a[1])];
    chips.innerHTML = entries.map(([k, n]) => {
      const on = k === "all" ? activeKinds.size === 0 : activeKinds.has(k);
      return '<span class="chip ' + (on ? "on" : "") + '" data-kind="' + esc(k) + '">' + esc(k) + '<span class="c">' + n + '</span></span>';
    }).join("");
    chips.querySelectorAll(".chip").forEach((c) => c.addEventListener("click", () => {
      const k = c.dataset.kind;
      if (k === "all") activeKinds.clear();
      else { activeKinds.has(k) ? activeKinds.delete(k) : activeKinds.add(k); }
      renderChips(); applyFilters();
    }));
  }

  function applyFilters() {
    let shown = 0;
    for (const row of rows) {
      const kindOk = activeKinds.size === 0 || activeKinds.has(row.dataset.kind);
      const qOk = !query || row.dataset.text.includes(query);
      const vis = kindOk && qOk;
      row.style.display = vis ? "" : "none";
      if (vis) shown++;
    }
    $("showing").textContent = events.length ? "showing " + shown + " of " + events.length : "";
  }

  function setStatus(s) {
    animateCount($("count"), s.count ?? 0);
    const badge = $("badge");
    if (s.ok === true) { badge.className = "badge ok"; badge.innerHTML = '<span class="pulse"></span> verified'; badSeq = null; markBad(); }
    else if (s.ok === false) { badge.className = "badge bad"; badge.innerHTML = '<span class="pulse"></span> tampered'; const m = /seq (\\d+)/.exec(s.detail || ""); badSeq = m ? +m[1] : null; markBad(); }
    else { badge.className = "badge"; badge.innerHTML = '<span class="pulse"></span> waiting'; }
    if (s.tail) { const t = $("tail"); t.textContent = s.tail.slice(0, 12) + "…"; t.dataset.copy = s.tail; }
  }
  function markBad() {
    for (const row of rows) row.classList.toggle("bad", badSeq !== null && +row.dataset.seq === badSeq);
    if (badSeq !== null) { const r = rows.find((x) => +x.dataset.seq === badSeq); if (r) { r.classList.add("open"); r.scrollIntoView({ block: "center", behavior: "smooth" }); } }
  }
  function animateCount(el, to) {
    const from = +el.textContent || 0; if (from === to) { el.textContent = to; return; }
    const t0 = performance.now(), dur = 380;
    (function step(t) { const p = Math.min(1, (t - t0) / dur); el.textContent = Math.round(from + (to - from) * (1 - Math.pow(1 - p, 3))); if (p < 1) requestAnimationFrame(step); })(t0);
  }

  // keyboard nav
  function visibleRows() { return rows.filter((r) => r.style.display !== "none"); }
  function setFocus(i) {
    const vis = visibleRows(); if (!vis.length) return;
    focusIdx = Math.max(0, Math.min(vis.length - 1, i));
    rows.forEach((r) => r.classList.remove("focus"));
    const r = vis[focusIdx]; r.classList.add("focus"); r.scrollIntoView({ block: "center", behavior: "smooth" });
  }
  document.addEventListener("keydown", (e) => {
    if (e.target.tagName === "INPUT" && e.key !== "Escape") return;
    if (e.key === "j" || e.key === "ArrowDown") { e.preventDefault(); setFocus(focusIdx + 1); }
    else if (e.key === "k" || e.key === "ArrowUp") { e.preventDefault(); setFocus(focusIdx - 1); }
    else if (e.key === "Enter" || e.key === " ") { const vis = visibleRows(); if (vis[focusIdx]) { e.preventDefault(); toggle(vis[focusIdx]); } }
    else if (e.key === "/") { e.preventDefault(); $("q").focus(); }
    else if (e.key === "f") { toggleFollow(); }
    else if (e.key === "?") { $("overlay").classList.toggle("show"); }
    else if (e.key === "Escape") { $("q").value = ""; query = ""; applyFilters(); rows.forEach((r) => r.classList.remove("open", "focus")); $("overlay").classList.remove("show"); $("q").blur(); }
  });

  function toggleFollow() { follow = !follow; const b = $("follow"); b.classList.toggle("on", follow); b.textContent = follow ? "● live" : "❚❚ paused"; }

  function connect(engagement) {
    if (es) es.close();
    events = []; rows = []; kinds = new Map(); activeKinds.clear(); query = ""; focusIdx = -1; badSeq = null;
    $("q").value = ""; $("eng-name").textContent = engagement; $("eng-target").textContent = "—";
    $("chips").innerHTML = ""; $("showing").textContent = "";
    stream.innerHTML = '<div class="empty">waiting for the first event…</div>';
    es = new EventSource("/events?engagement=" + encodeURIComponent(engagement));
    es.addEventListener("event", (e) => addEvent(JSON.parse(e.data)));
    es.addEventListener("status", (e) => setStatus(JSON.parse(e.data)));
    es.onerror = () => { const b = $("badge"); b.className = "badge"; b.innerHTML = '<span class="pulse"></span> reconnecting'; };
  }

  async function init() {
    $("follow").addEventListener("click", toggleFollow);
    $("help").addEventListener("click", () => $("overlay").classList.toggle("show"));
    $("overlay").addEventListener("click", (e) => { if (e.target.id === "overlay") $("overlay").classList.remove("show"); });
    $("tail").addEventListener("click", () => { if ($("tail").dataset.copy) copy($("tail").dataset.copy, $("tail")); });
    $("q").addEventListener("input", (e) => { query = e.target.value.trim().toLowerCase(); applyFilters(); });

    const res = await fetch("/list"); const { engagements } = await res.json();
    const pick = $("pick"); pick.innerHTML = "";
    for (const name of engagements) { const o = document.createElement("option"); o.value = name; o.textContent = name; pick.appendChild(o); }
    let current = qsEngagement() || engagements[0] || "";
    if (current) pick.value = current;
    pick.onchange = () => { const v = pick.value; history.replaceState(null, "", "?engagement=" + encodeURIComponent(v)); connect(v); };
    if (current) connect(current);
    else { stream.innerHTML = '<div class="empty">no engagements found under engagements/</div>'; $("eng-name").textContent = "no engagement"; }
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
