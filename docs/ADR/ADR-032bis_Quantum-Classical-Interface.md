# ADR-032bis: Quantum-Classical Interface
**Status:** Proposed  
**Date:** 2026-03-03  
**Authors:** Alessandro La Gamba  
**Deciders:** Architecture Team, Infrastructure Lead
**Extends:** ADR-032

## Context
ADR-032 defines the three-stage quantum backend abstraction but does not specify the kernel-to-QPU communication protocol. A formal interface is required for:
- **Thermal/power-aware scheduling:** QPU requires cryogenic cooling; cannot operate during eclipse or high-thermal-load maneuvers.
- **Graceful degradation:** Automatic fallback to simulation if QPU coherence time degrades (radiation-induced).
- **Multi-tenant access:** Constellation nodes may share a single QPU resource via time-slicing.

## Decision
Define QuantumAccelerator trait in Rust HAL (L0) with OCaml kernel bindings (L1).

### Interface Specification
```rust
// hal/src/quantum.rs
pub trait QuantumAccelerator: Send + Sync {
    /// Submit circuit, return future
    /// Async allows thermal/power scheduling by kernel
    async fn submit(&self, circuit: &QuantumCircuit) -> Result<Measurement, QError>;
    
    /// Check if QPU available (thermal/power constraints)
    fn status(&self) -> QuantumStatus;

    /// Fallback to classical simulation
    fn simulate(&self, circuit: &QuantumCircuit) -> Result<Measurement, QError>;

    /// Estimate resource requirements without execution
    fn estimate(&self, circuit: &QuantumCircuit) -> ResourceEstimate;
}

OCaml FFI Binding
ocaml
// kernel/quantum.ml
external quantum_submit : circuit -> (measurement, error) result = "rust_quantum_submit"
external quantum_status : unit -> status = "rust_quantum_status"

Rationale
Why Rust HAL with OCaml bindings?
Rust provides memory safety and concurrency guarantees required for hardware abstraction (L0). OCaml is used for the Kernel (L1) logic (per ADR-009). FFI allows type-safe communication between the two layers.
Why Async Submit?
Allows the kernel scheduler to pause quantum tasks during thermal events (eclipse) without blocking the main thread.
Consequences
Positive
Hardware-agnostic scheduling: Thermal-aware task distribution.
Automatic fallback: System remains operational even if QPU coherence degrades.
Multi-tenant support: Queue depth management allows resource sharing.
Negative / Mitigations
Additional FFI overhead: ~50μs per call.
Mitigation: Acceptable for non-real-time optimization tasks; batch circuit submission where possible.
OCaml async runtime integration: Requires careful handling of futures across language boundaries.
Mitigation: Use standardized Lwt/Async bridges defined in ADR-009.
Alternatives Rejected
Alternative
Reason Rejected

Alternative              | Reason Rejected
Direct C bindings        | Less type safety than Rust; higher risk of memory corruption in SEU environment.
Synchronous Interface    | Blocks kernel scheduler during QPU thermal checks; violates real-time constraints.
Network-based RPC        | Too much latency for onboard co-processor communication; PCIe/SpaceWire preferred.

Related
ADR-009: Idris 2 Specs — Defines kernel language constraints.
ADR-025: Energy Governance — Thermal constraints referenced in status check.
ADR-032: Quantum-Assisted Search — Defines the backend abstraction extended here.
TDD Reference
TDD v5.1, Part K: Quantum Architecture — Interface IDL definitions.
TDD_v5_2_Space_Computing_Extension
