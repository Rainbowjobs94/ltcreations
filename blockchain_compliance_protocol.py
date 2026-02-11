"""Compliance-gated blockchain + honesty escrow simulation (defensive demo).

This module merges the provided pseudo-code concepts into runnable Python:
- basic block + blockchain primitives
- compliance attestations hashed into block header
- 75/25 reward split with 5-year escrow model
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Dict, List, Tuple, Any


@dataclass
class Block:
    index: int
    timestamp_utc: str
    transactions: List[Dict[str, Any]]
    previous_hash: str
    compliance_data_hash: str
    nonce: int = 0
    block_hash: str = field(init=False)

    def __post_init__(self) -> None:
        self.block_hash = self.calculate_hash()

    def calculate_hash(self) -> str:
        raw = (
            f"{self.index}|{self.timestamp_utc}|{self.transactions}|"
            f"{self.previous_hash}|{self.compliance_data_hash}|{self.nonce}"
        )
        return sha256(raw.encode("utf-8")).hexdigest()


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
        return record.escrow_amount, victim

    def release_funds(self, *, block_height: int, caller: str, now_utc: datetime | None = None) -> int:
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
        return Block(
            index=0,
            timestamp_utc="2009-01-01T00:00:00Z",
            transactions=[{"type": "genesis"}],
            previous_hash="0",
            compliance_data_hash="0",
        )

    def get_latest_block(self) -> Block:
        return self.chain[-1]

    def add_block(self, block: Block) -> Block:
        block.previous_hash = self.get_latest_block().block_hash
        block.block_hash = block.calculate_hash()
        self.chain.append(block)
        return block


def perform_compliance_check() -> Tuple[bool, Dict[str, Any]]:
    """Collect compliance signals for demo purposes (replace with real verified APIs)."""
    compliance = {
        "verified_identity": True,
        "latitude": 49.2827,
        "longitude": -123.1207,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "compass_orientation": 270,
        "ambient_lux": 45000,
        "calculated_uv_index": 6,
        "weather": "Sunny",
    }
    return True, compliance


def compliance_hash(data: Dict[str, Any]) -> str:
    return sha256(str(sorted(data.items())).encode("utf-8")).hexdigest()


def mine_compliant_block(chain: Blockchain, transactions: List[Dict[str, Any]]) -> Block:
    ok, data = perform_compliance_check()
    if not ok:
        raise RuntimeError("Compliance check failed")

    block = Block(
        index=len(chain.chain),
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
        transactions=transactions,
        previous_hash=chain.get_latest_block().block_hash,
        compliance_data_hash=compliance_hash(data),
    )
    return chain.add_block(block)


if __name__ == "__main__":
    chain = Blockchain()
    escrow = HonestyEscrow()

    mined = mine_compliant_block(
        chain,
        transactions=[{"from": "Alice", "to": "Bob", "amount": 50}],
    )
    rec = escrow.create_escrow(notary="notary-001", reward_amount=1000, block_height=mined.index)

    print("Mined block:", mined.index, mined.block_hash[:16], "...")
    print("Compliance hash:", mined.compliance_data_hash[:16], "...")
    print("Escrow split:", {"liquid": rec.liquid_amount, "escrow": rec.escrow_amount})
