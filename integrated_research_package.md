# Integrated Research Package: Compliance Attestation + Environmental Integrity Stack

## 1) Cryptographic Encryption Protocol Review

### 1.1 Symmetric Encryption
- **AES-256-GCM**: recommended default for data-at-rest and service-to-service payload protection.
- **ChaCha20-Poly1305**: preferred where software-only performance and mobile CPU constraints matter.
- **Guideline**: Use AEAD modes only; avoid CBC unless legacy interop requires it.

### 1.2 Asymmetric Encryption
- **Ed25519**: preferred for digital signatures in modern APIs.
- **X25519**: preferred for key agreement.
- **RSA-3072+**: legacy compatibility only; avoid for greenfield unless regulatory requirement exists.

### 1.3 Hybrid Encryption
- Use **X25519 key exchange** + symmetric **AES-256-GCM** payload encryption.
- Envelope format:
  - ephemeral public key
  - recipient key ID
  - encrypted data key
  - ciphertext + nonce + auth tag

### 1.4 Post-Quantum Transition Strategy
- Recommended migration pattern: **hybrid classical + PQC** signatures and KEMs.
- Candidate algorithms (NIST trajectory aware):
  - **CRYSTALS-Kyber** (KEM)
  - **CRYSTALS-Dilithium** (signature)
- Rollout model:
  1. Add dual-signature support in attestation schema.
  2. Store verification metadata for classical and PQ signatures.
  3. Enforce dual validation in high-risk modes.

---

## 2) Production-Ready `ComplianceChecker` + Attestation Library

### 2.1 Functional Requirements
- Verify identity attestation proofs (placeholder or external KYC provider).
- Verify environmental sensor coherence (GPS, UV, lux, compass, timestamp).
- Produce canonical attestation payload hash.
- Sign attestation envelope with service key.
- Emit auditable verification report.

### 2.2 Python Reference Design

```python
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json

@dataclass
class SensorSnapshot:
    latitude: float
    longitude: float
    compass_deg: int
    ambient_lux: float
    uv_index: float
    timestamp_utc: str

class ComplianceChecker:
    def __init__(self, identity_provider, weather_provider, signer):
        self.identity_provider = identity_provider
        self.weather_provider = weather_provider
        self.signer = signer

    def verify_identity(self, subject_id: str) -> bool:
        return self.identity_provider.verify_subject(subject_id)

    def verify_environment(self, s: SensorSnapshot) -> dict:
        weather = self.weather_provider.lookup(s.latitude, s.longitude)
        uv_delta = abs(s.uv_index - weather["uv_index"])
        coherent = uv_delta <= 1.0 and 0 <= s.compass_deg <= 359 and s.ambient_lux >= 0
        return {
            "coherent": coherent,
            "uv_delta": uv_delta,
            "oracle_uv": weather["uv_index"],
            "oracle_weather": weather["weather"],
        }

    def canonical_attestation(self, subject_id: str, snapshot: SensorSnapshot, env_result: dict) -> str:
        payload = {
            "subject_id": subject_id,
            "snapshot": snapshot.__dict__,
            "env_result": env_result,
            "issued_at": datetime.now(timezone.utc).isoformat(),
            "schema": "attestation.v1",
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    def issue(self, subject_id: str, snapshot: SensorSnapshot) -> dict:
        if not self.verify_identity(subject_id):
            raise ValueError("Identity verification failed")

        env_result = self.verify_environment(snapshot)
        if not env_result["coherent"]:
            raise ValueError("Environmental coherence failed")

        canonical = self.canonical_attestation(subject_id, snapshot, env_result)
        digest = sha256(canonical.encode()).hexdigest()
        signature = self.signer.sign_hex_digest(digest)
        return {"canonical": canonical, "digest": digest, "signature": signature}
```

### 2.3 Data Flow Diagram

```text
[Client Sensors]
   | GPS/Lux/Compass/UV + timestamp
   v
[ComplianceChecker]
   |-- identity check --> [Identity Provider]
   |-- oracle check ----> [Weather/UV Oracle]
   |-- canonicalize + hash + sign
   v
[Attestation Envelope]
   | digest + signature + metadata
   v
[Block Builder / Ledger]
```

---

## 3) End-to-End Attestation Format Specification

### 3.1 Canonical JSON Schema (v1)

```json
{
  "schema": "attestation.v1",
  "subject": {
    "subjectId": "notary-001",
    "identityProofRef": "zkp://proof/abc123"
  },
  "context": {
    "timestampUTC": "2026-02-10T15:00:00Z",
    "geo": {"lat": 49.2827, "lon": -123.1207},
    "device": {
      "compassDeg": 270,
      "ambientLux": 45000,
      "deviceClass": "ios"
    },
    "environment": {
      "uvIndex": 6,
      "weather": "Sunny",
      "oracleRef": "oracle://weather/main/v1"
    }
  },
  "verification": {
    "coherent": true,
    "policyVersion": "policy-2026.02",
    "riskScore": 0.14
  },
  "integrity": {
    "canonicalization": "JCS",
    "hashAlg": "SHA-256",
    "digestHex": "..."
  },
  "signature": {
    "alg": "Ed25519",
    "keyId": "attestor-key-01",
    "sigBase64": "..."
  }
}
```

### 3.2 Verification Process
1. Parse and validate schema + required fields.
2. Re-canonicalize payload using exact canonicalization rule.
3. Recompute digest and compare with `integrity.digestHex`.
4. Resolve `keyId` and verify signature.
5. Re-evaluate policy constraints (timestamp freshness, geofence rules, oracle agreement).
6. Return verdict + reason codes.

### 3.3 Reason Codes (recommended)
- `E_SCHEMA_INVALID`
- `E_SIG_INVALID`
- `E_DIGEST_MISMATCH`
- `E_ORACLE_DISAGREEMENT`
- `E_SENSOR_OUT_OF_RANGE`
- `E_STALE_TIMESTAMP`

---

## 4) Sensor Spoofing Test Harness Design

### 4.1 Threat Scenarios
- GPS spoofing (coordinate jumps / impossible speed).
- UV spoofing (sensor value inconsistent with oracle + time of day).
- Lux spoofing (night-time high lux anomalies).
- Compass spoofing (impossible drift patterns).
- Replay attacks (old valid attestation resent later).

### 4.2 Harness Architecture

```text
[Test Driver]
  -> [Scenario Generator]
      -> clean data
      -> spoofed perturbations
  -> [ComplianceChecker Under Test]
  -> [Assertions + Metrics]
      -> detection rate
      -> false positive rate
      -> latency budget
```

### 4.3 Python Test Skeleton

```python
import pytest
from datetime import datetime, timedelta, timezone

@pytest.mark.parametrize("uv_sensor, uv_oracle, expected", [
    (6.0, 6.2, True),
    (2.0, 9.0, False),
])
def test_uv_coherence(uv_sensor, uv_oracle, expected, checker, snapshot_factory):
    s = snapshot_factory(uv_index=uv_sensor)
    checker.weather_provider.lookup = lambda lat, lon: {"uv_index": uv_oracle, "weather": "Sunny"}
    result = checker.verify_environment(s)
    assert result["coherent"] is expected


def test_replay_rejected(verifier, valid_attestation):
    verifier.verify(valid_attestation)
    replay = dict(valid_attestation)
    replay["context"]["timestampUTC"] = (datetime.now(timezone.utc) - timedelta(hours=4)).isoformat()
    verdict = verifier.verify(replay)
    assert verdict["ok"] is False
    assert "E_STALE_TIMESTAMP" in verdict["reasons"]
```

---

## 5) Tooling Recommendations (Requested Stack)

### 5.1 Swift / iPhone Sensor Integration
- **CoreLocation**: GPS/location updates.
- **CoreMotion**: orientation + motion signals.
- **AVFoundation** (camera-based brightness proxy where needed).
- **Combine**: streaming sensor pipeline.
- **CryptoKit**: local signing and key handling.

### 5.2 Web UI Frontend
- **React + TypeScript** (or Next.js for app shell).
- **Tailwind CSS** for rapid UI composition.
- **Zod** for schema validation.
- **TanStack Query** for API state.
- **Playwright** for e2e verification.

### 5.3 Deployment / CI-CD
- **Docker** + multi-stage builds.
- **GitHub Actions** quality gates:
  - lint
  - unit tests
  - type checks
  - security scans
- **Terraform/Pulumi** for infrastructure codification.
- **SBOM** generation + artifact signing.

### 5.4 Test Libraries
- **Rust backend**: `cargo test`, `proptest`, `tokio-test`.
- **Solidity contracts**: Foundry (`forge`) or Hardhat + Chai.
- **Frontend**: Vitest/Jest + Testing Library + Playwright.

---

## 6) Implementation Backlog (Actionable)

1. Extract attestation schema into `/schema/attestation.v1.json`.
2. Implement canonicalizer + signature verification module.
3. Add spoofing fixtures (`/tests/fixtures/spoofing/*.json`).
4. Integrate CI matrix for Python/Rust/Solidity/Frontend checks.
5. Add policy registry (`policy-YYYY.MM`) with reason-code mapping.

---

## 7) Safe Defaults and Risk Notes
- Never place raw identity documents on-chain.
- Store proof references + digests, not source artifacts.
- Enforce short attestation freshness window.
- Require independent oracle cross-check for environmental claims.
- Audit trail should be append-only and hash-linked.

---

## 8) Added Repository Capability Upgrades

This repository now includes:
- `bionexus_protocol_infographic.html` for an operator-facing protocol visualization dashboard.
- `generate_airainbowrepo_v3.py` to generate a reproducible `AiRainbowRepo_2026-02-10_123-7104_v3.0.zip` scaffold archive.

### Usage
```bash
python generate_airainbowrepo_v3.py
```

### Expected Output
```text
AiRainbowRepo_2026-02-10_123-7104_v3.0.zip
```
