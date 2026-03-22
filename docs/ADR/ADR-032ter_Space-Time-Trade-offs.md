# ADR-032ter: Space-Time Trade-offs (Proposed Extension)
**Status:** Proposed  
**Date:** 2026-03-03
**Extends:** ADR-031, ADR-032, ADR-032bis

# Context
Constellation nodes experience varying power availability based on orbital position (sunlit vs. eclipse). A node in eclipse (15-40W battery) cannot sustain QPU operation (50-100W cryogenic cooling), while sunlit nodes have surplus power.
Decision
Implement quantum load balancing: eclipse nodes offload quantum computation to sunlit peers via QKD-secured channels.
plain

Eclipse Node (low power)          Sunlit Node (surplus power)
┌─────────────────┐               ┌─────────────────┐
│ Problem encode  │──QKD key────►│  QPU execution  │
│ ZK-proof verify │◄─encrypted───│  Result + proof │
│                 │   result     │                 │
└─────────────────┘               └─────────────────┘

# Protocol Steps
Problem Encoding: Eclipse node encodes optimization/search problem as quantum circuit description (QASM-like IR)
Secure Transmission: QKD-derived one-time pad encrypts circuit + input data; authenticated via ADR-013 ZK identity
Remote Execution: Sunlit node executes on local QPU, generates ZK-proof of correct execution (Groth16 over circuit transcript)
Verification & Decryption: Eclipse node verifies ZK-proof (classical, <50ms), decrypts result, integrates into local state
# Resource Estimation
rust
// kernel/src/quantum/offload.rs
pub struct OffloadEstimate {
    pub circuit_size_qubits: u16,
    pub expected_runtime_ms: u32,
    pub encryption_overhead_bytes: usize,
    pub zk_proof_size_bytes: usize,  // ~1KB for Groth16
    pub total_latency_ms: u32,       // encode + encrypt + transmit + execute + verify + decrypt
}

impl OffloadEstimate {
    pub fn is_viable(&self, link_budget: &QKDLinkBudget) -> bool {
        self.total_latency_ms < link_budget.max_acceptable_latency_ms
            && self.encryption_overhead_bytes + self.zk_proof_size_bytes 
               < link_budget.mtu_bytes - protocol_overhead
    }
}

# Rationale

# Why Offload vs. Wait?
Waiting for eclipse end introduces unacceptable latency for time-sensitive optimization (e.g., collision avoidance, dynamic task reallocation). Offloading utilizes surplus energy elsewhere in the constellation, improving overall system throughput.
# Why QKD Security?
Quantum circuit descriptions may contain sensitive orbital data (debris trajectories, task assignments). QKD ensures information-theoretic security for the offload channel, meeting ADR-030 sovereignty requirements and ADR-013 zero-trust verification.
# Why ZK-Proofs for Remote Execution?
Eclipse node cannot trust sunlit peer's hardware (potential compromise, SEU-induced errors). ZK-proof provides cryptographic guarantee that:
Circuit was executed correctly per specification
Result was not tampered with during transmission
No side-channel leakage of sensitive inputs

# Consequences

# Positive
100% QPU utilization: Maximizes ROI on expensive quantum hardware across constellation
Eclipse continuity: Nodes retain quantum access even during power-constrained orbits
Natural load balancing: Orbital mechanics distribute load automatically (no central scheduler needed)
Enhanced security: QKD+ZK provides end-to-end verifiable confidentiality

# Negative / Mitigations
 
Issue                                                 | Mitigation
Requires QKD link (ADR-033)                           | QKD is already mandated for secure constellation comms; offload reuses existing infrastructure
Adds 1-2 RTT latency (~100-500ms LEO)                 | Acceptable for non-real-time optimization (trajectory planning vs. immediate control); ADR-032 auto-selects local execution for latency-critical tasks
ZK-proof generation overhead on sunlit node (~200ms)  | Offloaded tasks are high-value; proof generation cost is justified by verification trust; parallelize with other workloads
Increased protocol complexity                         | Encapsulate in QuantumAccelerator::submit() trait; application code unchanged

# Alternatives Rejected

Alternative                                           | Reason Rejected
Local Simulation during Eclipse                       | Falls back to classical speed; loses quantum advantage for critical problems; violates ADR-032 performance targets
Ground Offload                                        | Violates ADR-030 sovereignty; latency 1-22 minutes is too high for orbital operations; ground contact windows intermittent
Battery Overdraw                                      | Risks mission-critical power reserves; violates ADR-025 Energy Governance hard constraints
Pre-compute & Cache                                   | Infeasible for dynamic problems (anomaly detection, real-time task allocation); cache coherence overhead exceeds benefit

# Related

ADR-025: Energy Governance — Defines power budgets during eclipse/sunlit phases
ADR-032: Quantum-Assisted Search — Defines the workloads being offloaded (Grover, QAOA)
ADR-032bis: Quantum-Classical Interface — Defines the submission protocol extended for offload
ADR-033: QKD Link Specification — (Referenced) Secure channel requirements for offload traffic
ADR-013: Zero-Trust Verification — ZK-proof requirements for remote execution validation

# TDD Reference

- TDD v5.1, Part K: Quantum Architecture — Load balancing logic diagrams and sequence charts
- TDD v5.1, Part D.4: Security Protocols — QKD+ZK integration specifications for inter-node offload
- TDD_v5_2_Space_Computing_Extension
