import unittest
from datetime import datetime, timezone, timedelta

from compliance_checker import (
    ComplianceChecker,
    SensorSnapshot,
    StaticIdentityProvider,
    StaticWeatherOracle,
    DeterministicSigner,
    AttestationPolicy,
)


class SpoofingHarnessTests(unittest.TestCase):
    def setUp(self):
        self.checker = ComplianceChecker(
            StaticIdentityProvider(),
            StaticWeatherOracle(),
            DeterministicSigner(),
            policy=AttestationPolicy(max_uv_delta=1.0, max_age_seconds=120),
        )

    def _snap(self, **kw):
        data = {
            "latitude": 49.2827,
            "longitude": -123.1207,
            "compass_deg": 270,
            "ambient_lux": 45000,
            "uv_index": 6,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        }
        data.update(kw)
        return SensorSnapshot(**data)

    def test_happy_path(self):
        payload = self.checker.issue_attestation("notary-001", self._snap())
        self.assertTrue(payload["verification"]["coherent"])

    def test_uv_spoofing_detected(self):
        with self.assertRaisesRegex(ValueError, "E_ORACLE_DISAGREEMENT"):
            self.checker.issue_attestation("notary-001", self._snap(uv_index=15))

    def test_compass_spoofing_detected(self):
        with self.assertRaisesRegex(ValueError, "E_ORACLE_DISAGREEMENT"):
            self.checker.issue_attestation("notary-001", self._snap(compass_deg=700))

    def test_replay_detected(self):
        old = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        with self.assertRaisesRegex(ValueError, "E_STALE_TIMESTAMP"):
            self.checker.issue_attestation("notary-001", self._snap(timestamp_utc=old))


if __name__ == "__main__":
    unittest.main()
