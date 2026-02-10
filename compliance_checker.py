"""Production-ready compliance checker + attestation library (defensive reference).

Focus:
- canonical attestation payload
- integrity hash
- signature verification hooks
- environmental coherence policy checks
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any, Dict, Protocol, Tuple


class IdentityProvider(Protocol):
    def verify_subject(self, subject_id: str) -> bool: ...


class WeatherOracle(Protocol):
    def lookup(self, lat: float, lon: float) -> Dict[str, Any]: ...


class Signer(Protocol):
    def sign_hex_digest(self, hex_digest: str) -> str: ...


@dataclass
class SensorSnapshot:
    latitude: float
    longitude: float
    compass_deg: int
    ambient_lux: float
    uv_index: float
    timestamp_utc: str


@dataclass
class AttestationPolicy:
    max_uv_delta: float = 1.0
    max_age_seconds: int = 300
    compass_min: int = 0
    compass_max: int = 359


def canonicalize(obj: Dict[str, Any]) -> str:
    """Canonical JSON representation for deterministic hashing."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class ComplianceChecker:
    def __init__(
        self,
        identity_provider: IdentityProvider,
        weather_oracle: WeatherOracle,
        signer: Signer,
        policy: AttestationPolicy | None = None,
    ) -> None:
        self.identity_provider = identity_provider
        self.weather_oracle = weather_oracle
        self.signer = signer
        self.policy = policy or AttestationPolicy()

    def verify_identity(self, subject_id: str) -> bool:
        return self.identity_provider.verify_subject(subject_id)

    def verify_environment(self, snapshot: SensorSnapshot) -> Dict[str, Any]:
        oracle = self.weather_oracle.lookup(snapshot.latitude, snapshot.longitude)
        uv_delta = abs(float(snapshot.uv_index) - float(oracle["uv_index"]))
        compass_ok = self.policy.compass_min <= int(snapshot.compass_deg) <= self.policy.compass_max
        lux_ok = float(snapshot.ambient_lux) >= 0
        coherent = uv_delta <= self.policy.max_uv_delta and compass_ok and lux_ok
        return {
            "coherent": coherent,
            "uv_delta": uv_delta,
            "oracle_uv_index": oracle["uv_index"],
            "oracle_weather": oracle.get("weather", "unknown"),
            "compass_ok": compass_ok,
            "lux_ok": lux_ok,
        }

    def _validate_freshness(self, snapshot: SensorSnapshot) -> Tuple[bool, int]:
        ts = datetime.fromisoformat(snapshot.timestamp_utc.replace("Z", "+00:00"))
        age = int((datetime.now(timezone.utc) - ts).total_seconds())
        return age <= self.policy.max_age_seconds, age

    def issue_attestation(self, subject_id: str, snapshot: SensorSnapshot) -> Dict[str, Any]:
        if not self.verify_identity(subject_id):
            raise ValueError("E_IDENTITY_INVALID")

        is_fresh, age = self._validate_freshness(snapshot)
        if not is_fresh:
            raise ValueError("E_STALE_TIMESTAMP")

        env = self.verify_environment(snapshot)
        if not env["coherent"]:
            raise ValueError("E_ORACLE_DISAGREEMENT")

        payload = {
            "schema": "attestation.v1",
            "subject": {"subjectId": subject_id},
            "context": {
                "timestampUTC": snapshot.timestamp_utc,
                "geo": {"lat": snapshot.latitude, "lon": snapshot.longitude},
                "device": {
                    "compassDeg": snapshot.compass_deg,
                    "ambientLux": snapshot.ambient_lux,
                },
                "environment": {
                    "uvIndex": snapshot.uv_index,
                    "weather": env["oracle_weather"],
                },
            },
            "verification": {
                "coherent": True,
                "riskScore": round(min(env["uv_delta"] / max(self.policy.max_uv_delta, 0.0001), 1.0), 4),
                "ageSeconds": age,
            },
        }

        canonical = canonicalize(payload)
        digest = sha256(canonical.encode("utf-8")).hexdigest()
        sig = self.signer.sign_hex_digest(digest)

        payload["integrity"] = {
            "canonicalization": "JCS-like",
            "hashAlg": "SHA-256",
            "digestHex": digest,
        }
        payload["signature"] = {
            "alg": "Ed25519",
            "keyId": "attestor-key-01",
            "sigBase64": sig,
        }
        return payload


# Demo adapters
class StaticIdentityProvider:
    def verify_subject(self, subject_id: str) -> bool:
        return bool(subject_id and subject_id.startswith("notary-"))


class StaticWeatherOracle:
    def lookup(self, lat: float, lon: float) -> Dict[str, Any]:
        return {"uv_index": 6, "weather": "Sunny"}


class DeterministicSigner:
    def sign_hex_digest(self, hex_digest: str) -> str:
        return sha256(("sig:" + hex_digest).encode("utf-8")).hexdigest()


if __name__ == "__main__":
    checker = ComplianceChecker(StaticIdentityProvider(), StaticWeatherOracle(), DeterministicSigner())
    snap = SensorSnapshot(
        latitude=49.2827,
        longitude=-123.1207,
        compass_deg=270,
        ambient_lux=45000,
        uv_index=6,
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
    )
    result = checker.issue_attestation("notary-001", snap)
    print(result["integrity"]["digestHex"][:20], "...", result["verification"]) 
