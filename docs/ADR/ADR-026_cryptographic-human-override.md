# ADR-026: Cryptographic Human Override ("The Red Button")

**Status:** Proposed  
**Date:** 2026-02-26  
**Authors:** Alessandro La Gamba  
**Deciders:** Architecture team  

---

## Context

0xMeridian is designed to operate with minimal human intervention — *Fading Human Middleware* is a stated goal. However, autonomous systems operating in safety-critical domains (surgical robotics, autonomous vehicles, financial clearing, military) require an unconditional stop mechanism that:

1. **Cannot be disabled or delayed by any agent**, including a compromised or misbehaving one
2. **Cannot be spoofed** by a software-level message that mimics an override signal
3. **Is verifiable** — the operator can prove post-hoc that an override was issued and acted upon
4. **Is sovereign** — only designated human principals can issue it; no AI agent can self-issue or delegate it

EU AI Act Article 9 (Risk Management) and Article 14 (Human Oversight) mandate that high-risk AI systems provide human oversight mechanisms. This ADR is the technical implementation of that mandate.

---

## Decision

**Implement a Cryptographic Human Override using Ed25519 keys stored in hardware Secure Enclave (Apple Silicon) or TPM 2.0 (non-Apple). The override signal is verified at kernel ring-0 before any agent tick. No agent code path can intercept, delay, or reject a valid override.**

```rust
// kernel/src/override/red_button.rs

pub struct OverrideVerifier {
    /// Ed25519 verifying key, loaded from Secure Enclave at kernel boot.
    /// The signing key never leaves the hardware boundary.
    verifying_key: ed25519_dalek::VerifyingKey,
}

impl OverrideVerifier {
    /// Called by the kernel interrupt handler BEFORE any agent tick.
    /// Runs at ring-0; no agent can intercept.
    pub fn check_override(&self, signal: &OverrideSignal) -> OverrideResult {
        let msg = signal.canonical_bytes(); // deterministic serialisation
        match self.verifying_key.verify(&msg, &signal.signature) {
            Ok(_) => {
                audit_log::record_override(&signal); // immutable append-only log
                OverrideResult::Valid(signal.action)
            }
            Err(_) => OverrideResult::Invalid,
        }
    }
}

#[derive(Debug)]
pub struct OverrideSignal {
    pub timestamp_utc: i64,
    pub principal_id:  [u8; 32],  // SHA-256 of the operator's DID
    pub action:        OverrideAction,
    pub nonce:         [u8; 16],  // replay protection
    pub signature:     ed25519_dalek::Signature,
}

#[derive(Debug, Clone, Copy)]
pub enum OverrideAction {
    NetworkIsolate,    // Cut all Bus 4 / WireGuard connections
    AgentSwarmHalt,    // Suspend all agent ticks; kernel heartbeat continues
    FullShutdown,      // Graceful shutdown with state checkpoint
    SpecificAgentKill(AgentId), // Isolate a single misbehaving agent
}
```

### Override Execution Pipeline

```
Human Operator
      │  (presses hardware button / sends HSM-signed signal)
      │
      ▼
OverrideSignal {timestamp, principal_id, action, nonce, sig}
      │
      ▼
Kernel Interrupt Handler (ring-0, pre-agent-tick)
      │
      ├─── verify_ed25519(sig, verifying_key)
      │         │
      │    INVALID ──► discard, log attempt, alert security monitor
      │         │
      │     VALID ──►  audit_log::record_override(signal)      [immutable]
      │                     │
      │                     ├─ NetworkIsolate  ──► drop all WireGuard tunnels
      │                     ├─ AgentSwarmHalt  ──► park all agent OS threads
      │                     ├─ FullShutdown    ──► checkpoint → graceful exit
      │                     └─ AgentKill(id)   ──► sandbox isolate agent(id)
      │
      ▼
Override executed. Agent swarm has NO opportunity to respond.
```

### Key Management

| Component | Technology | Property |
|-----------|-----------|----------|
| Signing key (primary) | Ed25519 in Apple Secure Enclave / TPM 2.0 | Never exported; sign-only API |
| Signing key (backup) | Hardware Security Module (network HSM) | Remote override if primary device is compromised |
| Verifying key | Embedded in kernel binary at build time | Immutable after deployment |
| Key rotation | Offline ceremony (like ADR-010 MPC) | Requires physical access to new device + re-deployment |
| Nonce storage | Kernel ring-0 monotonic counter (persisted to NVM) | Prevents replay attacks |

### Audit Trail

Every override — valid or invalid — is written to an append-only audit log stored in two locations:

1. **Local NVM** (tamper-evident, kernel-managed, no agent write access)
2. **Remote ZK-verified log** (sent over Bus 4 to constellation nodes as a ZK-proven event, ADR-013)

```json
// Example audit record
{
  "event":        "OVERRIDE_EXECUTED",
  "timestamp":    "2026-02-26T14:23:01.042Z",
  "principal_id": "sha256:3f4a...",
  "action":       "AgentSwarmHalt",
  "nonce":        "a1b2c3d4e5f60001",
  "signal_hash":  "sha256:8c9d...",
  "kernel_tick":  9182736
}
```

---

## Rationale

**Why Ed25519 and not AES-256 HMAC:**  
HMAC requires the verifier to hold the secret key. If the kernel is compromised, the HMAC key is exposed and an attacker can forge valid signals. Ed25519 is asymmetric — the verifying key in the kernel verifies but cannot sign. The signing key never leaves the hardware boundary.

**Why kernel ring-0 and not agent-level:**  
Any implementation above ring-0 creates a surface where a compromised agent could intercept, delay, or drop the override signal. Ring-0 interrupt handlers execute before the OS scheduler resumes any user-space thread, making interception architecturally impossible.

**Why a hardware key (Secure Enclave / TPM) and not a software key:**  
Software keys can be extracted by an attacker with kernel-level access (e.g., a prompt-injection exploit that achieves code execution). The Secure Enclave and TPM 2.0 enforce a hardware boundary: the key is used but never revealed, even to the kernel itself.

**Why four distinct OverrideAction variants:**  
A binary "kill everything" switch is too coarse for operational use:
- `NetworkIsolate` is appropriate when a node is behaving correctly but must be quarantined from a compromised network
- `SpecificAgentKill` allows surgical intervention without stopping the entire swarm (e.g., isolating a misbehaving trading agent without halting the monitoring agents)
- `FullShutdown` is the last resort — it preserves state for forensic analysis

**Why a nonce (replay protection):**  
Without a nonce, a recorded valid override signal could be replayed by an attacker at a later time to shut down the system. The monotonic kernel counter ensures each signal is one-time-use.

---

## Consequences

**Positive:**
- EU AI Act Article 14 (Human Oversight) compliance: verifiable, auditable, unconditional
- No single agent can prevent shutdown — eliminates the "corrigibility" failure mode
- Audit trail is ZK-verifiable (ADR-013) — an external regulator can confirm an override was issued without seeing operational data
- Remote override via HSM enables satellite-based military kill switch and cloud-based enterprise emergency stop

**Negative / Mitigations:**
- **Single key single point of failure:** if the Secure Enclave device is destroyed, no override is possible → *mitigated by backup HSM with the same verifying key, plus physical network disconnection as a last resort*
- **Override latency ~50–200 ms** (HSM round-trip over satellite) → *mitigated by local device Secure Enclave for <5 ms local override; remote HSM is the backup path, not primary*
- **Key rotation complexity:** rotating the verifying key requires kernel re-deployment → *mitigated by key rotation ceremony documented in CONTRIBUTING.md; expected interval: yearly*
- **False positives:** accidental button press halts the swarm → *mitigated by `SpecificAgentKill` for targeted intervention and by requiring double-confirmation (two sequential signed signals within 5 s) for `FullShutdown`*

---

## Alternatives Rejected

| Alternative | Reason rejected |
|-------------|----------------|
| Software kill switch (SIGKILL to all agent processes) | A compromised agent with elevated privileges can intercept and ignore UNIX signals |
| Admin API endpoint (REST /override) | API can be blocked by a misbehaving agent or a network partition; not ring-0 |
| Physical power cut | Causes data loss and prevents graceful checkpoint; audit trail is lost |
| Agent consensus for shutdown | Circular dependency: a misbehaving majority could block the shutdown of a misbehaving minority |
| TOTP / OTP codes | Shared secret must be stored somewhere in the system; weaker than asymmetric hardware key |

---

## Related

- ADR-009: Idris 2 Specs — formal proof that the override handler has no reachable code path that skips verification
- ADR-012: WireGuard Mesh — `NetworkIsolate` terminates all WireGuard tunnels on the node
- ADR-013: ZK Proofs — override events are ZK-proven on the constellation audit log
- ADR-030: Constellation Governance — override signals propagate to all constellation nodes via Bus 4 when `action = NetworkIsolate`
- TDD v5.1, Parte H: Security Threat Model — override addresses Threat T-09 (Rogue Agent) and T-10 (Insider Threat)

---

## EU AI Act Compliance Mapping

| EU AI Act Article | Requirement | ADR-026 Implementation |
|-------------------|------------|----------------------|
| Art. 9 (Risk Management) | Risk mitigation measures for high-risk AI | Unconditional hardware-backed halt mechanism |
| Art. 14 (Human Oversight) | Enable human oversight and intervention | Override at ring-0, no agent can block |
| Art. 17 (Quality Management) | Logging and documentation | Append-only audit trail with ZK proofs |
| Art. 13 (Transparency) | Traceability of AI decisions | Every override logged with principal_id and action |
