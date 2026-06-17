"""Tamper-evident, hash-chained, append-only audit ledger.

Clean-room MIT port of Diogenes' ``DiogenesCore.AuditLog`` (Elixir). The chain
hash formula is identical; the Dilithium signature is replaced by an Ed25519
signature so a sealed bundle can be verified by anyone holding only the public
key — no shared secret required.

    signing    = seq_be64 || u32(len kind) || kind || hash_prev || u32(len payload) || payload
    sig        = Ed25519_sign(sk, signing)
    chain_hash = SHA256(signing || u32(len sig) || sig)

The variable-length fields (``kind``, ``payload``, ``sig``) are length-prefixed so
the encoding is **injective** — no two distinct ``(kind, payload)`` pairs can ever
serialize to the same signed bytes (a plain concatenation could, by sliding the
kind/payload boundary). ``hash_prev`` is a fixed 32 bytes and needs no prefix.

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
from collections.abc import Iterable
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

# Domain-separation tag for the detached signature over a sealed-bundle manifest,
# so a manifest signature can never be confused with a per-event signature (whose
# signing bytes begin with an 8-byte sequence number).
MANIFEST_SIG_CONTEXT: bytes = b"leash-audit-bundle-manifest-v1\x00"


def _seq_be64(seq: int) -> bytes:
    return seq.to_bytes(8, "big", signed=False)


def _u32(n: int) -> bytes:
    return n.to_bytes(4, "big", signed=False)


def _signing_bytes(seq: int, kind: str, hash_prev: bytes, payload: str) -> bytes:
    # Length-prefix the variable-length fields so the encoding is injective: two
    # distinct (kind, payload) pairs can never serialize to identical bytes (a bare
    # concatenation could, by shifting the kind/payload boundary). hash_prev is a
    # fixed 32 bytes, so it carries no prefix.
    kb = kind.encode("utf-8")
    pb = payload.encode("utf-8")
    return _seq_be64(seq) + _u32(len(kb)) + kb + hash_prev + _u32(len(pb)) + pb


def _chain_hash(seq: int, kind: str, hash_prev: bytes, payload: str, sig: bytes) -> bytes:
    h = hashlib.sha256()
    h.update(_signing_bytes(seq, kind, hash_prev, payload))
    h.update(_u32(len(sig)))
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

    def sign_manifest(self, manifest_bytes: bytes) -> bytes:
        """Detached Ed25519 signature over a sealed-bundle manifest, domain-separated
        from per-event signatures. Because the manifest carries the chain's
        ``event_count`` and ``chain_tail_hash``, signing it lets a holder of ONLY
        the public key detect *truncation* of the chain — dropping trailing events
        and re-deriving a consistent shorter manifest no longer verifies, since the
        attacker cannot forge this signature without the private key."""
        return self._sk.sign(MANIFEST_SIG_CONTEXT + manifest_bytes)

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
        instance resumes the chain instead of resetting it.

        Does NOT verify signatures — it recomputes ``chain_hash`` values
        mechanically to advance the tail pointer. Call ``verify_chain()`` for the
        full integrity proof.
        """
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


def verify_manifest_signature(
    public_key: Ed25519PublicKey, manifest_bytes: bytes, sig: bytes
) -> bool:
    """True iff ``sig`` is a valid detached signature over ``manifest_bytes`` under
    ``public_key`` (with the manifest domain-separation tag). Used by the bundle
    verifier to confirm the manifest — and thus the chain length/tail it commits
    to — was not altered or truncated by anyone lacking the private key."""
    try:
        public_key.verify(sig, MANIFEST_SIG_CONTEXT + manifest_bytes)
        return True
    except InvalidSignature:
        return False


def verify_ndjson(
    source: str | os.PathLike | Iterable[str], public_key: Ed25519PublicKey
) -> VerifyResult:
    """Walk an NDJSON ledger and confirm sequence order, chain linkage, and every
    signature. ``source`` may be a path (read from disk) or an iterable of already
    in-memory lines. Returns a falsy ``VerifyResult`` on the first violation."""
    lines = (
        Path(source).read_text(encoding="utf-8").splitlines()
        if isinstance(source, (str, os.PathLike))
        else source
    )
    prev = GENESIS
    expected_seq = 0
    for line in lines:
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

    return VerifyResult(
        True, f"Chain OK — {expected_seq} events, no tampering detected", tail_hash=prev.hex()
    )
