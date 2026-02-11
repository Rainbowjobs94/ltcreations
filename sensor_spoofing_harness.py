"""Modular spoofing/replay harness for compliance checker demo.

This file intentionally runs local simulations only and never performs live attacks.
It helps validate detection rules for inconsistent telemetry.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Tuple


@dataclass
class Telemetry:
    latitude: float
    longitude: float
    uv_index: int
    ambient_lux: int
    compass_orientation: int
    timestamp_utc: datetime


class TrustedOracle:
    def read(self) -> Telemetry:
        return Telemetry(
            latitude=49.2827,
            longitude=-123.1207,
            uv_index=6,
            ambient_lux=45000,
            compass_orientation=270,
            timestamp_utc=datetime.now(timezone.utc),
        )


class FakeGPSSpoofer:
    def apply(self, t: Telemetry) -> Telemetry:
        return Telemetry(
            latitude=t.latitude + 0.03,
            longitude=t.longitude - 0.04,
            uv_index=t.uv_index,
            ambient_lux=t.ambient_lux,
            compass_orientation=t.compass_orientation,
            timestamp_utc=t.timestamp_utc,
        )


class SensorReplay:
    def apply(self, t: Telemetry) -> Telemetry:
        return Telemetry(
            latitude=t.latitude,
            longitude=t.longitude,
            uv_index=t.uv_index,
            ambient_lux=t.ambient_lux,
            compass_orientation=t.compass_orientation,
            timestamp_utc=t.timestamp_utc - timedelta(minutes=25),
        )


class CompliancePolicy:
    def __init__(self, max_position_drift_deg: float = 0.01, max_age_minutes: int = 5) -> None:
        self.max_position_drift_deg = max_position_drift_deg
        self.max_age_minutes = max_age_minutes

    def verify(self, observed: Telemetry, oracle: Telemetry) -> Tuple[bool, str]:
        if abs(observed.latitude - oracle.latitude) > self.max_position_drift_deg:
            return False, "GPS_DRIFT_EXCEEDED"
        if abs(observed.longitude - oracle.longitude) > self.max_position_drift_deg:
            return False, "GPS_DRIFT_EXCEEDED"

        age = oracle.timestamp_utc - observed.timestamp_utc
        if age > timedelta(minutes=self.max_age_minutes):
            return False, "STALE_TELEMETRY"

        return True, "COMPLIANT"


def run_harness() -> Dict[str, Tuple[bool, str]]:
    oracle = TrustedOracle().read()
    policy = CompliancePolicy()

    baseline = oracle
    spoofed = FakeGPSSpoofer().apply(oracle)
    replayed = SensorReplay().apply(oracle)

    return {
        "baseline": policy.verify(baseline, oracle),
        "gps_spoof": policy.verify(spoofed, oracle),
        "sensor_replay": policy.verify(replayed, oracle),
    }


if __name__ == "__main__":
    results = run_harness()
    for scenario, (ok, reason) in results.items():
        print(f"{scenario}: ok={ok} reason={reason}")
