"""Tests for the viewer's HTTP layer — the security-sensitive surface around the
control channel (Origin/CSRF check, the engagement allowlist that prevents path
traversal, the body-size cap, and JSON/action validation). Driven against a real
``ThreadingHTTPServer`` over loopback so the actual request handling runs.
"""
import http.client
import json
import threading
from http.server import ThreadingHTTPServer

import pytest

import viewer.viewer as vv


@pytest.fixture
def server(tmp_path, monkeypatch):
    root = tmp_path / "engagements"
    (root / "demo").mkdir(parents=True)
    (root / "demo" / "audit.ndjson").write_text("")  # present → "demo" is a real engagement
    monkeypatch.setattr(vv, "ROOT", root)

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), vv._Handler)
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    host, port = httpd.server_address
    try:
        yield host, port, root
    finally:
        httpd.shutdown()
        httpd.server_close()


def _post(host, port, body, *, headers=None):
    conn = http.client.HTTPConnection(host, port, timeout=5)
    conn.request("POST", "/control", json.dumps(body),
                 {"Content-Type": "application/json", **(headers or {})})
    r = conn.getresponse()
    status, raw = r.status, r.read()
    conn.close()
    return status, raw


def _get(host, port, path):
    conn = http.client.HTTPConnection(host, port, timeout=5)
    conn.request("GET", path)
    r = conn.getresponse()
    status, raw = r.status, r.read()
    conn.close()
    return status, raw


def test_cross_origin_post_rejected(server):
    host, port, _ = server
    status, _ = _post(host, port, {"engagement": "demo", "action": "approve"},
                      headers={"Origin": "http://evil.example"})
    assert status == 403


def test_unknown_engagement_rejected(server):
    host, port, _ = server
    status, _ = _post(host, port, {"engagement": "nope", "action": "approve"})
    assert status == 404


def test_oversized_body_rejected(server):
    host, port, _ = server
    status, _ = _post(host, port, {"engagement": "demo", "action": "approve", "pad": "x" * 9000})
    assert status == 400


def test_unknown_action_rejected(server):
    host, port, _ = server
    status, _ = _post(host, port, {"engagement": "demo", "action": "drop_tables"})
    assert status == 400


def test_valid_approve_writes_decision(server):
    host, port, root = server
    status, raw = _post(host, port, {"engagement": "demo", "action": "approve", "gate_id": "gate-0"})
    assert status == 200
    assert json.loads(raw)["ok"] is True
    decision = root / "demo" / "control" / "decision.json"
    assert decision.exists()
    assert json.loads(decision.read_text())["action"] == "approve"


def test_halt_then_approve_rejected_over_http(server):
    host, port, _ = server
    assert _post(host, port, {"engagement": "demo", "action": "halt"})[0] == 200
    # The disk latch must reject a subsequent approve at the HTTP boundary too.
    status, raw = _post(host, port, {"engagement": "demo", "action": "approve", "gate_id": "gate-0"})
    assert status == 400
    assert json.loads(raw)["ok"] is False


def test_stream_unknown_engagement_404(server):
    host, port, _ = server
    # The allowlist also guards the read path: a crafted id cannot escape engagements/.
    assert _get(host, port, "/events?engagement=../../etc")[0] == 404
    assert _get(host, port, "/events?engagement=nope")[0] == 404


def test_list_reports_engagements(server):
    host, port, _ = server
    status, raw = _get(host, port, "/list")
    assert status == 200
    assert "demo" in json.loads(raw)["engagements"]
