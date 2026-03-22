# ADR-031: Hardware Specification for Sensor Nodes (UC02)

**Status:** Proposed  
**Date:** 2026-03-01  
**Authors:** Alessandro La Gamba  
**Deciders:** Architecture Team, Infrastructure Lead

---

## Context

The UC02 Counter-UAS Use Case mandates strict real-time performance metrics for edge sensor nodes (Node-2, Node-3, Node-4). Specifically, Node-3 (Electro-Optical) must perform concurrent AI inference (YOLOv8) and Zero-Knowledge Proof generation (Magellano Engine) within deterministic latency bounds.

**Performance Requirements (UC02 v2.0, Section 8):**
- Inference Latency: < 100ms (Edge)
- ZK-Proof Generation: < 500ms (GPU/ANE)
- Total Edge Processing: < 500ms (to meet <2s interdiction SLA)

**The Problem:**

Initial provisioning plans suggested using Apple Silicon M4 Base (16GB Unified Memory) for all sensor nodes to minimize CapEx. However, stress testing of the Magellano Inference Engine reveals that concurrent YOLOv8 inference and Groth16 proof generation are memory-intensive operations.

On 16GB configurations:
- **Memory Pressure:** OS + Magellano Context + YOLOv8 Weights + Video Buffers ≈ 14-15GB.
- **Swap Risk:** Under swarm attack scenarios (multi-target tracking), the system risks swapping to SSD.
- **Latency Jitter:** SSD swapping introduces non-deterministic latency spikes (>500ms), violating the UC02 interdiction SLA.

This decision record defines the minimum hardware specification required to guarantee Data Sovereignty (ADR-030) and Deterministic Latency without compromising on privacy or security.

---

## Decision

**Mandate Apple Silicon M4 Pro with minimum 24GB Unified Memory for Node-3 (Electro-Optical).**

### Hardware Specification Matrix

| Node Role | Minimum Chip | Minimum RAM | Storage | Justification |
|-----------|--------------|-------------|---------|---------------|
| **Node-1 (Command Hub)** | M2 Ultra / M4 Max | 64GB | 1TB SSD | Fusion Engine + Global Verifier + UI |
| **Node-2 (RF Sensor)** | M4 Pro | 24GB | 512GB SSD | SDR IQ Processing + ZK Proving |
| **Node-3 (Electro-Optical)** | M4 Pro | 24GB | 512GB SSD | YOLOv8 + Magellano Proving (Critical) |
| **Node-4 (Acoustic)** | M4 Base | 16GB | 256GB SSD | FFT/Audio Processing (Lower Load) |
| **Node-5 (Effector)** | M4 Pro | 24GB | 256GB SSD | Jamming Control + Safety Logic |

### Constraint

Node-3 must **NOT** deploy M4 Base (16GB) in production environments requiring <2s interdiction latency.

M4 Base (16GB) is permitted only for:
- Node-4 (Acoustic), or
- Node-3 in **Monitoring-Only Mode** (no interdiction capability)

### Magellano Configuration

```rust
// kernel/src/magellano/config.rs

pub struct MagellanoConfig {
    pub memory_reserve_gb: u8,      // Reserved for ZK Proving Context
    pub swap_policy: SwapPolicy,    // MUST be SwapPolicy::Disabled for Node-3
    pub ane_priority: PriorityLevel,// High for Inference
}

// Enforced at Node-3 bootstrap
if node_role == ELECTRO_OPTICAL && ram_gb < 24 {
    panic!("Node-3 requires minimum 24GB RAM for deterministic ZK-Proof generation");
}
```

---

## Rationale

**Why M4 Pro (24GB+) for Node-3?**

- **Memory Bandwidth:** M4 Pro offers higher memory bandwidth (~120GB/s vs ~100GB/s on Base), accelerating the matrix operations required for Groth16 proving.
- **Unified Memory Capacity:** 24GB provides a safe buffer above the ~15GB peak usage observed during multi-target tracking, preventing swap-induced latency jitter.
- **GPU Cores:** Additional GPU cores in the Pro chip accelerate the cryptographic hashing (SHA256/Merkle) required for ZK-Proof generation.

**Why not M4 Base (16GB)?**

- **Non-Deterministic:** While it can run the workload, it cannot guarantee the <100ms inference + <500ms proving SLA under load.
- **Safety Risk:** In a Counter-UAS scenario, latency jitter could mean the difference between a safe landing and a collision with critical infrastructure.

**Why Apple Silicon?**

- **Magellano Native:** The Magellano Engine is optimized for Apple Neural Engine (ANE) and Metal API. Porting to x86/Linux would incur a 3-5x latency penalty (ADR-003).
- **Secure Enclave:** Required for HSM operations (Key Storage, Biometric Hash) mandated by ADR-026 (Human Override).

---

## Consequences

**Positive:**
- **SLA Compliance:** Guarantees <500ms edge processing latency even under multi-target load.
- **Operational Safety:** Eliminates risk of system freeze during critical interdiction sequences.
- **Future Proofing:** 24GB RAM allows for larger model upgrades (e.g., YOLOv9/v10) without hardware replacement.
- **Resilience:** Reduces thermal throttling risk compared to pushing a Base chip to 100% memory capacity.

**Negative / Mitigations:**

- **Increased CapEx:** M4 Pro units cost approximately ~30% more than M4 Base.
  - *Mitigation:* Total system cost (5 nodes) remains ~50K€, significantly lower than Cloud-Centric OpEx (~200K€/yr).

- **Supply Chain:** M4 Pro configurations may have longer lead times than Base models.
  - *Mitigation:* Pre-provision spare nodes with approved specs for rapid deployment.

- **Power Consumption:** Slightly higher wattage under load.
  - *Mitigation:* ADR-025 (Energy Governance) ensures nodes enter Low-Power mode when no threats are detected.

---

## Alternatives Rejected

| Alternative | Reason Rejected |
|-------------|-----------------|
| **M4 Base (16GB) for All Nodes** | High risk of memory swapping on Node-3 during ZK-Proof generation. Violates UC02 Latency SLA (<500ms). |
| **Cloud Offloading for ZK-Proofs** | Violates ADR-030 (Data Sovereignty). Raw data would need to leave the edge for verification. Adds network latency (1-5s). |
| **x86/Linux + NVIDIA GPU** | Magellano Engine is native to Apple Silicon (ANE). Porting effort high. Power consumption 3x higher. No Secure Enclave for HSM. |
| **Reduce Model Size (YOLO-Nano)** | Reduces detection accuracy (mAP). UC02 requires <0.1% False Positive Rate, which demands YOLOv8-Large or similar. |
| **Disable ZK-Proofs on Node-3** | Violates ADR-013 (Zero-Trust Verification). Command Hub cannot verify optical detections mathematically. |

---

## Related

- **ADR-003:** Magellano HAL Specification — Defines the inference engine requirements.
- **ADR-013:** Zero-Trust Verification — Mandates ZK-Proofs for all sensor data.
- **ADR-025:** Energy Governance — Power management policies for edge nodes.
- **ADR-026:** Human Override Requirements — HSM and Secure Enclave usage.
- **ADR-030:** Federated Constellation Governance — Data sovereignty constraints.
- **UC02_Drone_Detection_v2.0:** Section 8 (Real-Time Performance Metrics).

---

## TDD Reference

- **TDD v5.1, Parte A.3:** Kernel Services — Hardware Abstraction Layer requirements.
- **TDD v5.1, Parte C.2:** UC02 Deployment Guide — Bill of Materials (BOM) updated to reflect M4 Pro requirement.
