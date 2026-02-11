"""Compliance-gated blockchain + honesty escrow simulation (defensive demo).

This module provides a practical, local-first reference for a
"Proof-of-Presence & Identity" workflow:
- canonical hashing + Merkle transaction root
- pluggable compliance checker with reason codes
- attestation payload model and verification path
- 75/25 reward split escrow with 5-year lock simulation

This is intentionally a prototype and not production code.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from typing import Any, Dict, List, Optional, Tuple


# -------------------------------
# Hashing and serialization utils
# -------------------------------


def canonical_serialize(data: Any) -> str:
    """Deterministic JSON encoding to avoid inconsistent hashes."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(payload: bytes) -> str:
    return sha256(payload).hexdigest()


def merkle_root(transactions: List[Dict[str, Any]]) -> str:
    """Return a simple SHA-256 Merkle root for a list of tx dictionaries."""
    if not transactions:
        return sha256_hex(b"")

    leaves = [sha256_hex(canonical_serialize(tx).encode("utf-8")) for tx in transactions]
    while len(leaves) > 1:
        nxt: List[str] = []
        for i in range(0, len(leaves), 2):
            left = leaves[i]
            right = leaves[i + 1] if i + 1 < len(leaves) else left
            nxt.append(sha256_hex(f"{left}{right}".encode("utf-8")))
        leaves = nxt
    return leaves[0]


# -------------------------------
# Attestation / compliance models
# -------------------------------


@dataclass
class AttestationPayload:
    device_id: str
    timestamp_utc: str
    latitude: float
    longitude: float
    compass_orientation: int
    ambient_lux: int
    uv_index: int
    nonce: str
    zkp_hash: str
    signer: str
    signature: str

    def digest(self) -> str:
        return sha256_hex(canonical_serialize(asdict(self)).encode("utf-8"))


@dataclass
class ComplianceResult:
    ok: bool
    reason_code: str
    evidence: Dict[str, Any]


class ComplianceChecker(ABC):
    """Interface to support different attestation/verification backends."""

    @abstractmethod
    def perform_check(self) -> ComplianceResult:
        raise NotImplementedError


def verify_attestation_payload(
    payload: AttestationPayload,
    *,
    now_utc: Optional[datetime] = None,
    max_age_minutes: int = 5,
) -> Tuple[bool, str]:
    """Apply baseline freshness/shape checks for an attestation payload.

    This is a lightweight stand-in for real cryptographic signature validation.
    """
    now_utc = now_utc or datetime.now(timezone.utc)
    try:
        payload_time = datetime.fromisoformat(payload.timestamp_utc)
    except ValueError:
        return False, "INVALID_TIMESTAMP_FORMAT"

    if payload_time.tzinfo is None:
        return False, "TIMESTAMP_MISSING_TIMEZONE"

    if now_utc - payload_time > timedelta(minutes=max_age_minutes):
        return False, "STALE_ATTESTATION"

    if not payload.signature or not payload.signer:
        return False, "MISSING_SIGNATURE_DATA"

    if not payload.device_id or not payload.nonce or not payload.zkp_hash:
        return False, "MISSING_ATTESTATION_FIELDS"

    return True, "ATTESTATION_VALID"


class DemoComplianceChecker(ComplianceChecker):
    """Mock checker with simple policy constraints and deterministic evidence."""

    def __init__(
        self,
        *,
        allowed_uv_max: int = 10,
        allowed_lux_min: int = 1000,
        max_attestation_age_minutes: int = 5,
    ) -> None:
        self.allowed_uv_max = allowed_uv_max
        self.allowed_lux_min = allowed_lux_min
        self.max_attestation_age_minutes = max_attestation_age_minutes

    def perform_check(self) -> ComplianceResult:
        payload = AttestationPayload(
            device_id="node-device-001",
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            latitude=49.2827,
            longitude=-123.1207,
            compass_orientation=270,
            ambient_lux=45000,
            uv_index=6,
            nonce="nonce-2026-demo",
            zkp_hash=sha256_hex(b"demo-zkp-proof"),
            signer="demo-attestor",
            signature="demo-signature",
        )

        valid, reason = verify_attestation_payload(
            payload,
            max_age_minutes=self.max_attestation_age_minutes,
        )
        if not valid:
            return ComplianceResult(False, reason, {"attestation": asdict(payload)})

        # Mock policy checks. In production, signature and quote verification
        # should happen against trusted roots + hardware attestation APIs.
        if payload.uv_index > self.allowed_uv_max:
            return ComplianceResult(False, "UV_LIMIT_EXCEEDED", {"attestation": asdict(payload)})
        if payload.ambient_lux < self.allowed_lux_min:
            return ComplianceResult(False, "LOW_LIGHT_ENVIRONMENT", {"attestation": asdict(payload)})

        return ComplianceResult(
            True,
            "COMPLIANT",
            {
                "attestation": asdict(payload),
                "attestation_digest": payload.digest(),
            },
        )


# -------------------------------
# Block and chain
# -------------------------------


@dataclass
class BlockHeader:
    index: int
    timestamp_utc: str
    previous_hash: str
    transaction_merkle_root: str
    compliance_data_hash: str
    nonce: int = 0


@dataclass
class Block:
    header: BlockHeader
    transactions: List[Dict[str, Any]]
    block_hash: str = field(init=False)

    def __post_init__(self) -> None:
        self.block_hash = self.calculate_hash()

    def calculate_hash(self) -> str:
        return sha256_hex(canonical_serialize(asdict(self.header)).encode("utf-8"))


@dataclass
class EscrowRecord:
    notary: str
    liquid_amount: int
    escrow_amount: int
    block_height: int
    release_timestamp_utc: datetime
    is_slashed: bool = False


class HonestyEscrow:
    """75/25 split: 25% immediate, 75% locked for 5 years."""

    def __init__(self) -> None:
        self.records: Dict[int, EscrowRecord] = {}

    def create_escrow(self, *, notary: str, reward_amount: int, block_height: int) -> EscrowRecord:
        if reward_amount <= 0:
            raise ValueError("Reward amount must be positive")

        liquid = reward_amount * 25 // 100
        escrow = reward_amount - liquid
        record = EscrowRecord(
            notary=notary,
            liquid_amount=liquid,
            escrow_amount=escrow,
            block_height=block_height,
            release_timestamp_utc=datetime.now(timezone.utc) + timedelta(days=365 * 5),
        )
        self.records[block_height] = record
        return record

    def slash_and_reimburse(self, *, block_height: int, victim: str) -> Tuple[int, str]:
        record = self.records[block_height]
        if record.is_slashed:
            raise ValueError("Escrow already slashed")
        record.is_slashed = True
        slashed = record.escrow_amount
        record.escrow_amount = 0
        return slashed, victim

    def release_funds(self, *, block_height: int, caller: str, now_utc: Optional[datetime] = None) -> int:
        record = self.records[block_height]
        now_utc = now_utc or datetime.now(timezone.utc)
        if caller != record.notary:
            raise PermissionError("Caller is not escrow owner")
        if record.is_slashed:
            raise ValueError("Escrow was slashed")
        if now_utc < record.release_timestamp_utc:
            raise ValueError("Escrow period not complete")
        amount = record.escrow_amount
        record.escrow_amount = 0
        return amount


class Blockchain:
    def __init__(self) -> None:
        self.chain: List[Block] = [self.create_genesis_block()]

    def create_genesis_block(self) -> Block:
        txs = [{"type": "genesis"}]
        header = BlockHeader(
            index=0,
            timestamp_utc="2009-01-01T00:00:00Z",
            previous_hash="0",
            transaction_merkle_root=merkle_root(txs),
            compliance_data_hash="0",
            nonce=0,
        )
        return Block(header=header, transactions=txs)

    def get_latest_block(self) -> Block:
        return self.chain[-1]

    def add_block(self, block: Block) -> Block:
        expected_prev = self.get_latest_block().block_hash
        if block.header.previous_hash != expected_prev:
            raise ValueError("previous_hash mismatch")

        expected_merkle = merkle_root(block.transactions)
        if block.header.transaction_merkle_root != expected_merkle:
            raise ValueError("transaction_merkle_root mismatch")

        recomputed = block.calculate_hash()
        if block.block_hash != recomputed:
            raise ValueError("block hash mismatch")

        self.chain.append(block)
        return block

    def validate_chain(self) -> Tuple[bool, str]:
        """Validate every block linkage and hash in the current chain."""
        if not self.chain:
            return False, "EMPTY_CHAIN"

        for index, block in enumerate(self.chain):
            if block.block_hash != block.calculate_hash():
                return False, f"HASH_MISMATCH_AT_{index}"

            if block.header.transaction_merkle_root != merkle_root(block.transactions):
                return False, f"MERKLE_MISMATCH_AT_{index}"

            if index == 0:
                continue

            prev = self.chain[index - 1]
            if block.header.previous_hash != prev.block_hash:
                return False, f"LINK_MISMATCH_AT_{index}"

        return True, "CHAIN_VALID"


# -------------------------------
# Mining flow
# -------------------------------


def mine_compliant_block(
    chain: Blockchain,
    transactions: List[Dict[str, Any]],
    checker: Optional[ComplianceChecker] = None,
) -> Block:
    checker = checker or DemoComplianceChecker()
    result = checker.perform_check()
    if not result.ok:
        raise RuntimeError(f"Compliance check failed: {result.reason_code}")

    latest = chain.get_latest_block()
    header = BlockHeader(
        index=len(chain.chain),
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
        previous_hash=latest.block_hash,
        transaction_merkle_root=merkle_root(transactions),
        compliance_data_hash=sha256_hex(canonical_serialize(result.evidence).encode("utf-8")),
        nonce=0,
    )
    return chain.add_block(Block(header=header, transactions=transactions))


if __name__ == "__main__":
    chain = Blockchain()
    escrow = HonestyEscrow()

    mined = mine_compliant_block(
        chain,
        transactions=[
            {"from": "Alice", "to": "Bob", "amount": 50},
            {"from": "Carol", "to": "Dave", "amount": 25},
        ],
    )
    rec = escrow.create_escrow(notary="notary-001", reward_amount=1000, block_height=mined.header.index)

    is_valid, status = chain.validate_chain()
    print("Mined block:", mined.header.index, mined.block_hash[:16], "...")
    print("Merkle root:", mined.header.transaction_merkle_root[:16], "...")
    print("Compliance hash:", mined.header.compliance_data_hash[:16], "...")
    print("Escrow split:", {"liquid": rec.liquid_amount, "escrow": rec.escrow_amount})
    print("Chain validation:", is_valid, status)
