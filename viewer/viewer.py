"""viewer — live audit stream + operator Control Center for a Leash engagement.

Tails ``engagements/<id>/audit.ndjson`` over Server-Sent Events and renders the
governance story live: every event as it lands, the running chain-tail hash, the
event count, a VERIFIED / TAMPERED badge re-derived on each append, a live
vulnerability feed, and a swarm Control Center from which the operator drives the
human approval gate and the kill-switch.

The viewer never writes to the ledger — the engagement is the single ledger
writer. An operator action (APPROVE / HALT) is posted to ``/control``, which
drops a decision file the running engagement picks up and records as a governed
event (see ``swarm.control_channel``). So even the operator's clicks land in the
tamper-evident chain, signed by the one writer.

Built on the standard library's ``http.server`` rather than FastAPI/uvicorn: a
local SSE tail + a one-shot control POST need no framework, and zero extra deps
keeps the demo one ``python -m`` away with nothing to install. The UI lives in
``viewer/index.html`` (read per request, so it hot-reloads while iterating) and
follows the Roan Co. design language.

    python -m viewer.viewer                 # serve on http://localhost:8089
    python -m viewer.viewer --port 9000
    python -m viewer.viewer --engagement control-demo
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
from swarm.control_channel import submit_decision

ROOT = Path(os.getenv("LEASH_ENGAGEMENTS", "engagements"))
INDEX_PATH = Path(__file__).parent / "index.html"
POLL_SECONDS = 0.5
MAX_BODY = 8192  # control POSTs are tiny; cap to refuse anything that isn't


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

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/control":
            self.send_error(404)
            return
        # CSRF defense for a localhost operator tool: a cross-origin page must not
        # be able to drive the gate. The viewer's own page sends an Origin equal to
        # the Host we serve; reject anything else. Origin-less callers (curl, local
        # scripts) are allowed — they are not browsers carrying ambient state.
        origin = self.headers.get("Origin")
        if origin:
            host = self.headers.get("Host", "")
            if origin not in (f"http://{host}", f"https://{host}"):
                self._serve_json({"ok": False, "detail": "cross-origin control rejected"}, code=403)
                return
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length <= 0 or length > MAX_BODY:
            self._serve_json({"ok": False, "detail": "empty or oversized body"}, code=400)
            return
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self._serve_json({"ok": False, "detail": "invalid JSON"}, code=400)
            return

        engagement = str(body.get("engagement", ""))
        action = str(body.get("action", ""))
        gate_id = str(body.get("gate_id", ""))[:64]
        operator = (str(body.get("operator", "")) or "operator")[:64]

        # Allowlist defense: only an engagement that actually exists on disk is
        # accepted, so a crafted id can never escape the engagements/ tree.
        if engagement not in _engagements():
            self._serve_json({"ok": False, "detail": "unknown engagement"}, code=404)
            return
        if action not in ("approve", "halt"):
            self._serve_json({"ok": False, "detail": "unknown action"}, code=400)
            return
        try:
            rec = submit_decision(
                engagement, action=action, gate_id=gate_id, operator=operator, root=str(ROOT)
            )
        except ValueError as e:
            self._serve_json({"ok": False, "detail": str(e)}, code=400)
            return
        self._serve_json({"ok": True, "detail": f"{action} recorded", "decision": rec})

    # ----- responses -----------------------------------------------------
    def _serve_json(self, obj: dict, *, code: int = 200) -> None:
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_index(self) -> None:
        try:
            body = INDEX_PATH.read_text(encoding="utf-8").encode("utf-8")
        except FileNotFoundError:
            self.send_error(500, f"UI missing: {INDEX_PATH}")
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_stream(self, engagement: str) -> None:
        if not engagement:
            self.send_error(400, "missing ?engagement=")
            return
        # Same allowlist defense the write path uses: only a real engagement dir
        # is streamable, so `?engagement=../../x` cannot read outside engagements/.
        if engagement not in _engagements():
            self.send_error(404, "unknown engagement")
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


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Live audit stream + Control Center for a Leash engagement.")
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
