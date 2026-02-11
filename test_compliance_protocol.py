import unittest
from datetime import datetime, timedelta, timezone

from blockchain_compliance_protocol import (
    AttestationPayload,
    Blockchain,
    ComplianceChecker,
    ComplianceResult,
    DemoComplianceChecker,
    HonestyEscrow,
    mine_compliant_block,
    verify_attestation_payload,
)
from sensor_spoofing_harness import run_harness


class RejectingChecker(ComplianceChecker):
    def perform_check(self) -> ComplianceResult:
        return ComplianceResult(ok=False, reason_code="FORCED_REJECT", evidence={})


class ProtocolTests(unittest.TestCase):
    def test_attestation_freshness_check(self) -> None:
        old_payload = AttestationPayload(
            device_id="d1",
            timestamp_utc=(datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(),
            latitude=1.0,
            longitude=1.0,
            compass_orientation=1,
            ambient_lux=10000,
            uv_index=2,
            nonce="n",
            zkp_hash="z",
            signer="s",
            signature="sig",
        )
        valid, reason = verify_attestation_payload(old_payload)
        self.assertFalse(valid)
        self.assertEqual(reason, "STALE_ATTESTATION")

    def test_mine_and_validate_chain(self) -> None:
        chain = Blockchain()
        block = mine_compliant_block(chain, [{"from": "A", "to": "B", "amount": 1}], DemoComplianceChecker())
        self.assertEqual(block.header.index, 1)
        ok, reason = chain.validate_chain()
        self.assertTrue(ok)
        self.assertEqual(reason, "CHAIN_VALID")

    def test_rejecting_checker_raises(self) -> None:
        chain = Blockchain()
        with self.assertRaises(RuntimeError):
            mine_compliant_block(chain, [{"from": "A", "to": "B", "amount": 1}], RejectingChecker())

    def test_escrow_release_and_slash(self) -> None:
        escrow = HonestyEscrow()
        rec = escrow.create_escrow(notary="n1", reward_amount=1000, block_height=1)
        with self.assertRaises(ValueError):
            escrow.release_funds(block_height=1, caller="n1")

        released = escrow.release_funds(
            block_height=1,
            caller="n1",
            now_utc=rec.release_timestamp_utc + timedelta(seconds=1),
        )
        self.assertEqual(released, 750)

        rec2 = escrow.create_escrow(notary="n2", reward_amount=1000, block_height=2)
        expected_slashed = rec2.escrow_amount
        slashed, victim = escrow.slash_and_reimburse(block_height=2, victim="victim")
        self.assertEqual((slashed, victim), (expected_slashed, "victim"))

    def test_spoofing_harness(self) -> None:
        results = run_harness()
        self.assertEqual(results["baseline"], (True, "COMPLIANT"))
        self.assertEqual(results["gps_spoof"], (False, "GPS_DRIFT_EXCEEDED"))
        self.assertEqual(results["sensor_replay"], (False, "STALE_TELEMETRY"))


if __name__ == "__main__":
    unittest.main()
