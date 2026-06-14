"""Tests for the tamper-evident audit ledger — including the core claim that
any post-hoc edit to the chain is detectable."""
import json

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from governance.audit_ledger import AuditLedger, verify_ndjson


async def test_clean_chain_verifies(tmp_path):
    ledger = AuditLedger("clean", root=tmp_path)
    await ledger.append("tool_call", json.dumps({"tool": "http_probe", "target": "localhost:3000"}))
    await ledger.append("tool_result", json.dumps({"status": 200, "findings": ["sqli_candidate"]}))

    result = ledger.verify_chain()
    assert result.ok, result.detail
    assert "2 events" in result.detail


async def test_tamper_is_detected(tmp_path):
    ledger = AuditLedger("tampered", root=tmp_path)
    await ledger.append("tool_call", json.dumps({"tool": "http_probe", "target": "localhost:3000"}))
    await ledger.append("tool_result", json.dumps({"finding": "none"}))
    pubkey = ledger.public_key_bytes()

    # An attacker rewrites the first event's payload to hide where the swarm went.
    lines = ledger.path.read_text().splitlines()
    record = json.loads(lines[0])
    record["payload"] = json.dumps({"tool": "http_probe", "target": "evil.example.com"})
    lines[0] = json.dumps(record)
    ledger.path.write_text("\n".join(lines) + "\n")

    result = verify_ndjson(ledger.path, Ed25519PublicKey.from_public_bytes(pubkey))
    assert not result.ok
    assert "seq 0" in result.detail


async def test_replay_resumes_chain(tmp_path):
    ledger = AuditLedger("resume", root=tmp_path)
    await ledger.append("open", json.dumps({"engagement": "demo-01"}))

    # A fresh instance over the same directory must resume the chain, not reset it.
    reopened = AuditLedger("resume", root=tmp_path)
    await reopened.append("close", json.dumps({"engagement": "demo-01"}))

    result = reopened.verify_chain()
    assert result.ok, result.detail
    assert "2 events" in result.detail


async def test_third_party_verify_with_public_key_only(tmp_path):
    ledger = AuditLedger("thirdparty", root=tmp_path)
    await ledger.append("open", json.dumps({"engagement": "demo-01"}))
    await ledger.append("tool_result", json.dumps({"vuln": "sqli", "endpoint": "/rest/products/search"}))

    # A regulator with only the public key and the NDJSON can verify the chain.
    pubkey = ledger.public_key_bytes()
    result = verify_ndjson(ledger.path, Ed25519PublicKey.from_public_bytes(pubkey))
    assert result.ok, result.detail
