# ADR-013: Zero-Knowledge Execution Proofs (Groth16)

**Status:** Accepted  
**Date:** 2026-02-17  
**Authors:** Alessandro La Gamba  
**Deciders:** Architecture team  

---

## Context

In a federated constellation of AI OS nodes (ADR-030), nodes must prove to each other that they have correctly executed their assigned tasks — without revealing the input data, model weights, or private context. Trust must not be assumed; it must be mathematically verified.

The same requirement applies within a single node for compliance: regulatory auditors (GDPR, MDR, MiFID II) must be able to verify that the AI system processed data according to declared policies, without seeing the data itself.

Three approaches to verifiable computation were evaluated:
- **Option A:** Trusted Execution Environments (SGX/SEV) with remote attestation
- **Option B:** Homomorphic Encryption (CKKS/BFV)
- **Option C:** Zero-Knowledge Proofs (Groth16 / PLONK)

---

## Decision

**Groth16 proofs on BLS12-381 curve. Per-batch execution proofs: every 100ms window of agent executions generates a single Groth16 proof. Proof size: 192 bytes. Verification: <2ms (O(1) in circuit size). Proving: ~100ms on Metal GPU, ~500ms on CPU.**

```
┌──────────────────────────────────────────────────────────────────┐
│                    ZK EXECUTION PROOF PIPELINE                   │
│                                                                  │
│  Agent Executions (100ms window)                                 │
│  [E0, E1, E2, ..., E_n] → Serialize → [R0, R1, ..., R_n]       │
│                                              │                   │
│                                    SIMD Merkle Root (ADR-011)   │
│                                              │                   │
│                                         root_hash               │
│                                              │                   │
│  Private Witness:              Public Inputs:                    │
│  - input_data                  - root_hash                       │
│  - model_weights               - output_hash                    │
│  - intermediate_acts           - timestamp                       │
│  - agent_state                 - agent_id                        │
│                  └──────────────────┘                            │
│                           │                                      │
│                    Groth16 Prove                                  │
│                  (ZkProver, Rust/bellman)                        │
│                           │                                      │
│                  ExecutionProof (192 bytes)                      │
│                    {π_A, π_B, π_C}                               │
│                           │                                      │
│             ┌─────────────┴─────────────┐                        │
│             ▼                           ▼                        │
│    Local Audit Log               Bus 4 → Constellation           │
│    (tamper-evident)              (verifiable by any node)        │
└──────────────────────────────────────────────────────────────────┘
```

### Groth16 Proof Structure

```rust
/// 192-byte Groth16 proof on BLS12-381
pub struct ExecutionProof {
    /// π_A: G1 point (48 bytes compressed)
    pi_a: G1Affine,
    /// π_B: G2 point (96 bytes compressed)
    pi_b: G2Affine,
    /// π_C: G1 point (48 bytes compressed)
    pi_c: G1Affine,
}

/// Public inputs to the circuit (known to verifier)
pub struct ProofPublicInputs {
    merkle_root:   [u8; 32],   // commitment to all executions in batch
    output_hash:   [u8; 32],   // hash of agent outputs
    agent_id:      [u8; 16],   // UUID of proving agent
    timestamp_ms:  u64,        // Unix timestamp of batch start
    batch_size:    u32,        // number of executions in batch
}
```

### Verification (3 pairing operations)

```rust
pub fn verify_execution_proof(
    pvk:    &PreparedVerifyingKey<Bls12_381>,
    proof:  &ExecutionProof,
    inputs: &ProofPublicInputs,
) -> Result<(), ProofError> {
    // Groth16 verification equation:
    // e(π_A, π_B) = e(α, β) · e(Σ x_i·w_i, γ) · e(π_C, δ)
    //
    // 3 pairing operations on BLS12-381 → always <2ms regardless of circuit size
    let inputs_linear = inputs.to_linear_combination(&pvk.gamma_abc_g1);
    groth16::verify_proof(pvk, proof, &[inputs_linear])
        .map_err(|e| ProofError::VerificationFailed { detail: e.to_string() })
}
```

### Performance Profile

| Metric | Value | Notes |
|--------|-------|-------|
| Proof size | 192 bytes | Fixed regardless of circuit complexity |
| Verification time | <2ms | O(1) — always 3 pairings |
| Proving time (Metal GPU) | ~100ms | MSM + NTT via Metal compute shaders |
| Proving time (CPU SIMD) | ~500ms | Fallback for non-Apple targets |
| Circuit constraints | ~1M (R1CS) | Simplified Magellano inference circuit |
| Trusted setup (one-time) | ~10s | MPC ceremony (ADR-010) |
| Proving Key size | ~100MB | Loaded on SSD, read on demand |

---

## Rationale

### Why ZK Proofs over TEE attestation (Option A)

TEE (Trusted Execution Environment) remote attestation requires:
- Hardware support (Intel SGX, AMD SEV) — not universally available
- The verifier trusts the hardware manufacturer (Intel, AMD)
- Attestation reveals the code being executed — not zero-knowledge

ZK Proofs have no hardware dependency and the verifier trusts only mathematics, not any manufacturer.

### Why Groth16 over PLONK

| Property | Groth16 | PLONK |
|----------|---------|-------|
| Proof size | 192 bytes (smallest) | 512+ bytes |
| Verification time | <2ms (3 pairings) | ~5ms |
| Proving time | ~100ms | ~200ms |
| Trusted setup | Per-circuit (MPC ceremony done once) | Universal (simpler) |
| Recursion support | Limited (via Nova extension) | Native |
| Maturity | Production (Zcash, Filecoin) | Newer |

For 0xMeridian's use case (fixed circuit, production deployment), Groth16's smaller proofs and faster verification outweigh PLONK's flexibility advantage.

### Why BLS12-381 curve

- **128-bit security level** — industry standard for long-term proofs
- **Pairing-friendly** — required for Groth16
- **Standardized** in Ethereum, Zcash, Filecoin — mature tooling in the `bellman` and `ark-works` Rust crates
- **Compressed points** — G1 at 48 bytes, G2 at 96 bytes = 192 byte total proof

### Why per-100ms batching

Generating one proof per execution would require 100ms × (number of executions/second) of proving time. Batching 100ms of executions into a single proof amortizes the 100ms proving cost over potentially hundreds of executions, keeping the proof overhead <1% of wall-clock time.

---

## Consequences

**Positive:**
- 192-byte proofs — minimal Bus 4 overhead
- <2ms verification — negligible cost for any receiving node
- Compliance audit: regulatory bodies verify execution correctness without data exposure
- Universal verifiability: any node with the Verifying Key can check proofs

**Negative / Mitigations:**
- **~100MB Proving Key on SSD:** Must be loaded for proof generation → *streamed from SSD on demand; not resident in RAM permanently*
- **Circuit changes require new MPC ceremony:** → *circuit is designed as stable; behavioral updates go through QLoRA adapters (ADR-008), not circuit changes*
- **Proving time 100ms limits batch frequency:** Cannot prove faster than 100ms window → *design choice; 100ms batches are sufficient for all identified use cases*

---

## Alternatives Rejected

| Alternative | Reason rejected |
|-------------|----------------|
| TEE remote attestation (SGX/SEV) | Hardware-dependent; manufacturer trust required; not zero-knowledge |
| Homomorphic Encryption (CKKS/BFV) | 1000× slower than ZK proving; not practical for 100ms cycles |
| STARK proofs | Larger proofs (10–100KB vs 192B); no trusted setup needed but verification is slower |
| Audit logs with signatures | Provable integrity but not zero-knowledge — data must be revealed for audit |
| PLONK | Larger proofs, slower verification — inferior tradeoff for fixed-circuit deployment |

---

## Related

- ADR-010: MPC Ceremony — generates the Proving Key used here
- ADR-011: SIMD Merkle — computes the Merkle root that is the primary public input
- ADR-020: Bellman Groth16 Integration — circuit definition and R1CS compilation
- ADR-030: Federated Constellation — proofs are exchanged over Bus 4 as ZK-SLA attestations
- TDD v5.1, Parte K: ZK Layer implementation details
