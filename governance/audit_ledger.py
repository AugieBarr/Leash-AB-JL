"""Tamper-evident, hash-chained, append-only audit ledger.

Clean-room MIT port of Diogenes' ``DiogenesCore.AuditLog`` (Elixir). The chain
hash formula is identical; the Dilithium signature is replaced by an Ed25519
signature so a sealed bundle can be verified by anyone holding only the public
key — no shared secret required.

    sig        = Ed25519_sign(sk, seq_be64 || kind || hash_prev || payload)
    chain_hash = SHA256(seq_be64 || kind || hash_prev || payload || sig)

The next event's ``hash_prev`` binds to the previous event's ``chain_hash``, so
altering any earlier payload, kind, or signature invalidates every following
link. Genesis ``hash_prev`` is 32 zero bytes.

On-disk format is NDJSON (one JSON object per line) at
``engagements/<id>/audit.ndjson``, with ``hash_prev`` and ``sig`` base64-encoded.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

GENESIS: bytes = b"\x00" * 32


def _seq_be64(seq: int) -> bytes:
    return int(seq).to_bytes(8, "big", signed=False)


def _signing_bytes(seq: int, kind: str, hash_prev: bytes, payload: str) -> bytes:
    return _seq_be64(seq) + kind.encode("utf-8") + hash_prev + payload.encode("utf-8")


def _chain_hash(seq: int, kind: str, hash_prev: bytes, payload: str, sig: bytes) -> bytes:
    h = hashlib.sha256()
    h.update(_seq_be64(seq))
    h.update(kind.encode("utf-8"))
    h.update(hash_prev)
    h.update(payload.encode("utf-8"))
    h.update(sig)
    return h.digest()


@dataclass(frozen=True)
class LedgerHead:
    seq: int
    prev_hash: bytes


@dataclass(frozen=True)
class VerifyResult:
    ok: bool
    detail: str
    tail_hash: str = ""  # hex of the final chain_hash on success; "" on failure

    def __bool__(self) -> bool:
        return self.ok


class AuditLedger:
    """Async-safe, file-backed, hash-chained audit ledger for one engagement."""

    def __init__(self, engagement_id: str, root: str | os.PathLike = "engagements") -> None:
        self.engagement_id = engagement_id
        self.dir = Path(root) / engagement_id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "audit.ndjson"
        self.key_path = self.dir / "engagement_ed25519.key"
        self._lock = asyncio.Lock()
        self._sk = self._load_or_generate_key()
        self._pk = self._sk.public_key()
        self._seq, self._prev = self._replay_tail()

    # ----- keys ----------------------------------------------------------
    def _load_or_generate_key(self) -> Ed25519PrivateKey:
        if self.key_path.exists():
            return Ed25519PrivateKey.from_private_bytes(self.key_path.read_bytes())
        sk = Ed25519PrivateKey.generate()
        raw = sk.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
        self.key_path.write_bytes(raw)
        os.chmod(self.key_path, 0o600)
        return sk

    def public_key_bytes(self) -> bytes:
        """Raw Ed25519 public key — ship this in the sealed bundle so any third
        party can verify the chain without the private key."""
        return self._pk.public_bytes(Encoding.Raw, PublicFormat.Raw)

    # ----- append --------------------------------------------------------
    async def append(self, kind: str, payload: str) -> int:
        """Append one signed event and return its sequence number. Atomic under
        an asyncio lock so concurrent callers cannot interleave the chain (the
        race the Elixir ``append_head`` fix addresses)."""
        async with self._lock:
            seq, prev = self._seq, self._prev
            sig = self._sk.sign(_signing_bytes(seq, kind, prev, payload))
            record = {
                "seq": seq,
                "kind": kind,
                "payload": payload,
                "hash_prev": base64.b64encode(prev).decode("ascii"),
                "sig": base64.b64encode(sig).decode("ascii"),
            }
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
            self._prev = _chain_hash(seq, kind, prev, payload, sig)
            self._seq = seq + 1
            return seq

    @property
    def head(self) -> LedgerHead:
        return LedgerHead(self._seq, self._prev)

    @property
    def tail_hash_hex(self) -> str:
        return self._prev.hex()

    # ----- replay --------------------------------------------------------
    def _replay_tail(self) -> tuple[int, bytes]:
        """Recover ``(next_seq, prev_hash)`` from an existing ledger so a fresh
        instance resumes the chain instead of resetting it."""
        if not self.path.exists():
            return 0, GENESIS
        seq, prev = 0, GENESIS
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            hash_prev = base64.b64decode(rec["hash_prev"])
            sig = base64.b64decode(rec["sig"])
            prev = _chain_hash(rec["seq"], rec["kind"], hash_prev, rec["payload"], sig)
            seq = rec["seq"] + 1
        return seq, prev

    # ----- verify --------------------------------------------------------
    def verify_chain(self, public_key: bytes | None = None) -> VerifyResult:
        pk = (
            Ed25519PublicKey.from_public_bytes(public_key)
            if public_key is not None
            else self._pk
        )
        return verify_ndjson(self.path, pk)


def verify_ndjson(path: str | os.PathLike, public_key: Ed25519PublicKey) -> VerifyResult:
    """Walk an NDJSON ledger and confirm sequence order, chain linkage, and
    every signature. Returns a falsy ``VerifyResult`` on the first violation."""
    prev = GENESIS
    expected_seq = 0
    text = Path(path).read_text(encoding="utf-8")
    for line in text.splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        seq = rec["seq"]
        kind = rec["kind"]
        payload = rec["payload"]
        hash_prev = base64.b64decode(rec["hash_prev"])
        sig = base64.b64decode(rec["sig"])

        if seq != expected_seq:
            return VerifyResult(False, f"sequence gap: expected {expected_seq}, got {seq}")
        if hash_prev != prev:
            return VerifyResult(False, f"chain break at seq {seq}")
        try:
            public_key.verify(sig, _signing_bytes(seq, kind, hash_prev, payload))
        except InvalidSignature:
            return VerifyResult(False, f"bad signature at seq {seq}")

        prev = _chain_hash(seq, kind, hash_prev, payload, sig)
        expected_seq += 1

    return VerifyResult(True, f"Chain OK — {expected_seq} events, no tampering detected")
