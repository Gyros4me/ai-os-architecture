# ADR-032: Quantum-Assisted Search for Space Computing (UC03)
**Status:** Proposed  
**Date:** 2026-03-03  
**Authors:** Alessandro La Gamba  
**Deciders:** Architecture Team, Infrastructure Lead
**Extends:** ADR-009, ADR-011, ADR-013, ADR-004, ADR-025, ADR-030, ADR-031

## Context
0xMeridian's terrestrial search architecture (FAISS vector similarity + BM25 sparse retrieval) becomes intractable in the space computing domain due to three fundamental constraints:
- **Latency Budget:** Ground contact windows of 8-15 minutes (LEO) or 3-22 minute one-way delays (deep space) make cloud offloading impossible. All search must complete onboard with deterministic bounds.
- **Power Envelope:** 50-200W solar-budgeted operations cannot sustain brute-force O(N) or O(N²) algorithms for N > 10⁶ states (trajectory optimization, anomaly detection).
- **SEU Environment:** 1-200 bit-flips/MB/day from cosmic radiation corrupt classical search indices; quantum-inspired data structures offer inherent error-detection through amplitude encoding.

Three search problems exceed classical polynomial-time tractability in orbital operations:
1. **Orbital Trajectory Optimization:** kⁿ search space where k=maneuver options, n=decision horizons (rendezvous with non-cooperative debris)
2. **Anomaly Pattern Search:** 10K+ sensor channels at 100Hz, sparse labeled data, requiring O(n²) correlation mining per timestep
3. **Multi-Satellite Task Allocation:** NP-hard bin-packing with coverage windows, power budgets, and contact constraints

Current quantum hardware (NISQ era: 100-1000 noisy qubits) is insufficient for fault-tolerant deployment before 2028-2030. However, quantum-inspired classical algorithms and hybrid quantum-classical simulation provide immediate value while building the architecture for native quantum advantage.

## Decision
Implement a three-stage quantum search architecture: Stage 1 (2026-2028) quantum-inspired QRAM + QAOA simulation on NPU; Stage 2 (2028-2031) hybrid QPU co-processor interface; Stage 3 (2031+) native fault-tolerant quantum. All stages maintain zero-regression classical fallback.

### Core Components
- **Quantum Backend Abstraction (Rust):** Defines `QuantumBackend` trait for execution, status, simulation, and selection.
- **Grover's Algorithm:** Orbital implementation for unstructured search (Trajectory/Sensor patterns).
- **QAOA:** For Constellation Task Allocation (NP-hard optimization).
- **SEU-Resilient Execution:** Three-layer protection (Algorithmic, Error Correction, Physical).
- **Quantum-Inspired QRAM:** Stage 1 data structure for SEU-hardened search.

## Rationale
### Why three stages instead of waiting for fault-tolerant quantum?
Space missions operate on 5-15 year timelines. A "quantum-only" architecture would be undeployable until 2030+, missing the 2026-2028 market window. The staged approach delivers value at every phase.

### Why Grover for unstructured search vs. quantum annealing?
Grover's algorithm is universal: any search problem with a verifiable oracle can be accelerated. Quantum annealing requires problem-specific embedding and has limited connectivity.

### Why QAOA for optimization vs. VQE?
QAOA is explicitly designed for constraint satisfaction problems (MAX-CUT, graph coloring, scheduling) with proven approximation ratios. VQE is for quantum Hamiltonians (chemistry).

### Why Steane [[7,1,3]] code?
The Steane code is the smallest CSS code that corrects all single-qubit errors. It requires only 7 physical qubits per logical qubit, critical for early NISQ-era space QPUs.

### Why quantum-inspired QRAM instead of classical FAISS?
FAISS is brittle under SEU corruption. A tree structure enables checksums at every node; corruption is detected at the first access. The O(log N) query complexity provides deterministic latency bounds.

## Consequences
### Positive
- **Provable speedup:** Grover provides O(√N) vs O(N) for unstructured search; QAOA within 95% of optimal for 50-task allocation.
- **Hardware-agnostic interface:** QuantumBackend trait allows seamless swap from simulation to real QPU.
- **SEU resilience:** Three-layer protection maintains >99.5% circuit fidelity in LEO radiation environment.
- **Zero regression:** Classical FAISS + simulated annealing fallback always available.

### Negative / Mitigations
- **Stage 1 QAOA simulation overhead:** +200ms vs classical SA for small N.
  - *Mitigation:* Auto-select classical SA for N <20; quantum-inspired only for N >100.
- **Stage 2 QPU hardware cost:** ~$500K per satellite.
  - *Mitigation:* Optional upgrade; constellation can mix QPU-equipped and classical-only nodes.
- **ZK circuit development:** 2-4 weeks engineering per new task type.
  - *Mitigation:* Pre-built circuit library for 10 common patterns.
- **Power consumption:** QPU cryogenic cooling requires 50-100W additional power.
  - *Mitigation:* ADR-025 Energy Governor disables QPU during eclipse.

## Alternatives Rejected
| Alternative | Reason Rejected |
| --- | --- |
| Full quantum deployment now (2026) | Hardware not available; no fault-tolerant QPU exists; would delay program 5+ years. |
| Pure classical FAISS | Insufficient for N >1M orbital states; O(N) latency violates real-time constraints; no SEU resilience. |
| Quantum annealing (D-Wave) | Problem-specific embedding required; limited connectivity; not embeddable in satellite SWaP. |
| Blockchain-based task ledger | 12-15s latency unacceptable for real-time task allocation; energy consumption incompatible with solar power. |
| Centralized ground-based quantum | Violates ADR-030 sovereignty; ground contact windows too infrequent; latency 1-22 minutes. |

## Related
- ADR-004: Gossip+Raft — constellation uses SWIM gossip for membership.
- ADR-009: Idris 2 Specs — quantum circuit specifications extracted to OCaml.
- ADR-011: SIMD Merkle — hash functions for quantum circuit verification.
- ADR-013: ZK Execution Proofs — verification of quantum computation correctness.
- ADR-025: Energy Governance — QPU power management during eclipse cycles.
- ADR-030: Federated Constellation Governance — multi-node quantum task distribution.
- ADR-031: Hardware Specification for Sensor Nodes — Edge compute baseline.

## TDD Reference
- TDD v5.1, Part K: Quantum Architecture — full circuit diagrams and Protobuf schemas.
- TDD_v5_2_Space_Computing_Extension