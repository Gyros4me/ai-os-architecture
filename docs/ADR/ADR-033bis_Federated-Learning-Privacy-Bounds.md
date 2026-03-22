# ADR-033bis: Federated Learning Privacy Bounds

**Status:** Proposed  
**Date:** 2026-03-03  
**Authors:** Alessandro La Gamba  
**Deciders:** Architecture Team, Infrastructure Lead  
**Extends:** ADR-033, ADR-030, ADR-013

## Context

ADR-033 FEDERATED-QLoRA transmits encrypted gradients between constellation nodes via DTN Bundle Protocol. While CKKS (homomorphic encryption) prevents eavesdropping by intermediate nodes, the Raft leader (elected aggregator) receives all decrypted gradients for FedAvg computation. This creates a single point of privacy failure: a compromised or malicious leader can inspect individual gradients Gᵢ and reconstruct sensitive training data through gradient inversion attacks.

Standard federated learning frameworks (PySyft, Flower) rely on a "honest-but-curious" security model inappropriate for:
- Multi-national constellations (EU-USA-Japan data sharing without mutual legal frameworks)
- Military-civilian dual-use missions (classified observations alongside commercial data)
- Competitive commercial operators (SpaceX, Amazon Kuiper) sharing infrastructure

Differential privacy (DP) in ADR-033 provides membership protection but does not prevent the aggregator from seeing raw gradients. A cryptographic guarantee is required: no single party ever observes individual gradients in unmasked form.

## Decision

Implement Secure Multi-Party Computation (SMPC) with pairwise masking: gradients are cryptographically masked such that the aggregator computes the exact average without ever decrypting individual contributions. Combined with ZK-proofs of correct masking.

Standard FedAvg (vulnerable):
┌─────────┐     ┌─────────┐     ┌─────────┐
│ Node 1  │────►│         │     │         │
│ Node 2  │────►│ Leader  │────►│  ΣGᵢ/n  │──► Model Update
│ Node 3  │────►│ (sees   │     │         │
│   ...   │────►│ all Gᵢ) │     │         │
└─────────┘     └─────────┘     └─────────┘
▲ Privacy breach: leader compromised
▲ Gradient inversion → data reconstruction
Secure Aggregation (ADR-033bis):
┌─────────┐     ┌─────────┐     ┌─────────┐
│ Node 1  │────►│         │     │         │
│   G₁    │     │         │     │         │
│ +R₁₂-R₁₃│     │  Leader │     │  Σ(Gᵢ   │
├─────────┤     │  (sees  │     │  +masks)│──► ΣGᵢ/n
│ Node 2  │────►│  only   │────►│  masks  │
│   G₂    │     │  masked │     │  cancel │
│ +R₂₃-R₂₁│     │  sums)  │     │         │
├─────────┤     │         │     │         │
│ Node 3  │────►│         │     │         │
│   G₃    │     │         │     │         │
│ +R₃₁-R₃₂│     │         │     │         │
└─────────┘     └─────────┘     └─────────┘
▲ No single node knows others' masks
▲ Leader sees only G₁+G₂+G₃ (sum, not individuals)
▲ ZK-proof verifies correct masking without revealing Rᵢ
plain


## Core Components

### 1. Pairwise Masking Protocol

For n nodes, each node i generates n−1 random masks Rᵢⱼ for j≠i. The mask sent to leader is:

Mᵢ = Gᵢ + Σⱼ≠i (Rᵢⱼ − Rⱼᵢ) (mod p)

Where:
- Rᵢⱼ = mask node i shares with node j (agreed via Diffie-Hellman)
- Rⱼᵢ = mask node j shares with node i (cancels in aggregation)
- p = large prime for finite field arithmetic

**Aggregation property:**
Σᵢ₌₁ⁿ Mᵢ = Σᵢ₌₁ⁿ Gᵢ + Σᵢ₌₁ⁿ Σⱼ≠i (Rᵢⱼ − Rⱼᵢ) = Σᵢ₌₁ⁿ Gᵢ

All masks cancel (telescoping sum), leaving exact gradient sum without individual exposure.

### 2. Mask Agreement via Bus-4

```rust
// kernel/src/federation/mask_agreement.rs

pub struct MaskAgreement {
    node_id: NodeId,
    dh_keypair: X25519KeyPair,           // Ephemeral, per-round
    peer_masks: HashMap<NodeId, Scalar>, // R_ij for each peer j
}

impl MaskAgreement {
    /// Phase 1: Broadcast DH public keys
    pub fn broadcast_key(&self, bus: &mut Bus4) -> Result<(), BusError> {
        let msg = MaskKeyBroadcast {
            node_id: self.node_id,
            dh_public: self.dh_keypair.public,
            round_id: current_round(),
        };
        bus.gossip_broadcast(msg)
    }
    
    /// Phase 2: Compute shared secrets and derive masks
    pub fn compute_masks(&mut self, peer_keys: &[MaskKeyBroadcast]) {
        for peer in peer_keys {
            if peer.node_id == self.node_id { continue; }
            
            let shared_secret = self.dh_keypair.compute_shared(&peer.dh_public);
            let mask = hkdf_derive_mask(&shared_secret, self.node_id, peer.node_id);
            
            // R_ij = +mask if i < j, -mask if i > j (ensures R_ij = -R_ji)
            let signed_mask = if self.node_id < peer.node_id { 
                mask 
            } else { 
                -mask 
            };
            
            self.peer_masks.insert(peer.node_id, signed_mask);
        }
    }
    
    /// Apply masking to gradient
    pub fn mask_gradient(&self, gradient: &Gradient) -> MaskedGradient {
        let total_mask: Scalar = self.peer_masks.values().sum();
        gradient.add_scalar(total_mask)
    }
}

3. ZK-Proof of Correct Masking
Each node must prove it applied masking correctly without revealing Rᵢⱼ:
rust

pub struct MaskingProof {
    pub commitment: PedersenCommitment,  // Commits to G_i and masks
    pub proof: Groth16Proof,             // 192 bytes
}

impl MaskingProof {
    /// Prove: M_i = G_i + Σ(R_ij - R_ji) AND R_ij derived from DH shared secret
    pub fn prove(
        gradient: &Gradient,
        masks: &HashMap<NodeId, Scalar>,
        dh_secrets: &[SharedSecret],
    ) -> Self {
        let circuit = MaskingCircuit {
            private_gradient: gradient.hide(),           // Hidden input
            private_masks: masks.values().cloned().collect(),
            private_secrets: dh_secrets.to_vec(),
            public_masked: gradient.add_masks(masks),    // Public output
        };
        
        Groth16::prove(&MASKING_CRS, circuit)
    }
    
    /// Verify without knowing gradient or masks
    pub fn verify(&self, masked_gradient: &MaskedGradient) -> bool {
        Groth16::verify(
            &MASKING_VK,
            &self.proof,
            &[masked_gradient.to_field_element(), self.commitment.to_field()]
        )
    }
}

Public inputs: Mᵢ (masked gradient), commitment to Gᵢ
Private inputs: Gᵢ, all Rᵢⱼ, DH shared secrets
Constraint: Mᵢ = Gᵢ + Σⱼ≠i(Rᵢⱼ − Rⱼᵢ) AND Rᵢⱼ = HKDF(DHᵢⱼ)
4. Full Aggregation Protocol
plain

SECURE FEDERATED ROUND (ADR-033 + ADR-033bis)
───────────────────────────────────────────────
Phase A: MASK AGREEMENT [T+0..5% of orbit]
 1. Each node generates ephemeral X25519 keypair
 2. Gossip broadcast DH public keys to all peers
 3. Compute shared secrets with each peer
 4. Derive masks R_ij = HKDF(shared_secret, i, j, round_id)
 5. Sign commitment to masking: H(G_i, R_i1, ..., R_in)

Phase B: MASKED GRADIENT SUBMISSION [T+5%..10%]
 1. Compute local gradient G_i via AUTONOMOUS-QLoRA
 2. Apply masking: M_i = G_i + Σ(R_ij - R_ji)
 3. Generate ZK-proof of correct masking
 4. Send to leader: {M_i, proof, commitment, signature}

Phase C: VERIFICATION & AGGREGATION [T+10%..15%]
 1. Leader verifies all ZK-proofs (parallel, <100ms each)
 2. Reject invalid masks (reputation penalty -0.1)
 3. Sum valid M_i: ΣM_i = ΣG_i (masks cancel)
 4. Compute average: G_agg = ΣM_i / n
 5. Generate ZK-proof of correct aggregation
 6. Broadcast G_agg + proof to all nodes

Phase D: UNMASKING & DEPLOYMENT [T+15%..20%]
 1. Each node verifies aggregation proof
 2. Deploy G_agg via hot-swap (identical to ADR-033)
 3. Verify Critic score improvement ≥5%
 4. Rollback if verification fails

 5. Dropout Resilience
If node j drops out after mask agreement but before aggregation, its masks Rⱼᵢ and Rᵢⱼ are unknown. The sum ΣMᵢ retains −Rⱼᵢ or +Rᵢⱼ terms that don't cancel.
Solution: Secret Sharing via VSS (Verifiable Secret Sharing)
rust

pub struct MaskShare {
    pub shares: Vec<SecretShare>,  // Distributed to t+1 peers
    pub commitment: FeldmanCommitment,  // Verifiable reconstruction
}

impl MaskAgreement {
    /// Share each R_ij with t+1 peers (t = maximum tolerated dropouts)
    pub fn share_masks(&self) -> HashMap<NodeId, MaskShare> {
        self.peer_masks.iter().map(|(peer, mask)| {
            let shares = shamir_share(mask, threshold=t+1, shares=n-1);
            let commitment = feldman_commit(&shares);
            (peer.clone(), MaskShare { shares, commitment })
        }).collect()
    }
    
    /// Reconstruct missing mask if peer drops out
    pub fn reconstruct_mask(
        &self,
        missing_peer: NodeId,
        received_shares: &[SecretShare]
    ) -> Option<Scalar> {
        if received_shares.len() < t+1 { return None; }
        Some(shamir_reconstruct(received_shares))
    }
}

Rationale
Why pairwise masking vs. homomorphic encryption (HE) for aggregation?
HE (CKKS, BFV) allows computation on encrypted data but has 100-1000× overhead. A single FedAvg with HE-encrypted gradients of 35MB requires 3-5 seconds on optimized hardware—unacceptable for 90-minute orbit rounds. Pairwise masking has <5% overhead (XOR or modular addition) and provides equivalent security with ZK verification.
Why ZK-proof of masking vs. optimistic execution?
Without ZK verification, a malicious node could submit arbitrary Mᵢ (not Gᵢ+masks) to poison the global model. The ZK constraint system enforces that Mᵢ was correctly derived from a valid gradient and honestly computed masks.
Why Diffie-Hellman vs. pre-shared keys?
Ephemeral DH provides forward secrecy: compromise of long-term keys doesn't reveal past round masks. Per-round key rotation limits breach window to single federation round.
Why tolerate only t < n/3 dropouts?
Byzantine fault tolerance bound: with VSS reconstruction, the protocol remains secure and live if fewer than 1/3 of nodes are malicious or unavailable. Matches Raft consensus assumptions in ADR-030.
Consequences
Positive
Cryptographic privacy: No single party (including leader) observes individual gradients; mathematical guarantee stronger than policy/trust
Byzantine robustness: Malicious nodes cannot poison aggregation without detection (ZK-proof verification)
Forward secrecy: Ephemeral keys prevent retroactive decryption of past rounds
Minimal overhead: <5% latency increase vs. standard FedAvg; <10% bandwidth for VSS shares
Negative / Mitigations
Table

| Issue                                                                            | Mitigation                                                                                                              |
| -------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| Communication overhead: 2× messages for mask agreement (DH key exchange)         | Overlap with Phase A local training; keys are small (32 bytes X25519 public)                                            |
| Computation cost: ZK-proof generation ~200ms per node                            | Parallel proving on ANE; batched verification on leader; amortized over 90-minute round                                 |
| Dropout complexity: VSS reconstruction requires t+1 peers to respond             | Set t=1 for 5-node constellation (tolerate 1 dropout); deep space missions use larger t                                 |
| Setup ceremony: Trusted setup required for Groth16 CRS (Common Reference String) | Use MPC ceremony (similar to Zcash Sapling); refresh CRS annually; fallback to STARKs (no trusted setup, larger proofs) |

Integration with ADR-033
ADR-033bis extends ADR-033 FEDERATED-QLoRA as a privacy layer:
Table

| Feature                  | ADR-033                           | ADR-033bis Extension                               |
| ------------------------ | --------------------------------- | -------------------------------------------------- |
| Gradient encryption      | CKKS (confidentiality in transit) | Pairwise masking (confidentiality from aggregator) |
| Aggregation verification | ZK-proof of correct FedAvg        | ZK-proof of correct masking + FedAvg               |
| Dropout handling         | Retry or exclude                  | VSS reconstruction                                 |
| Threat model             | Honest-but-curious                | Malicious majority (up to t < n/3)                 |
| Proof size               | 192 bytes                         | 192 bytes (same Groth16)                           |

Deployment: ADR-033bis is optional enhancement. Constellations with high trust (single operator) use ADR-033 only. Multi-national or competitive constellations enable ADR-033bis via configuration flag.
Related
ADR-011: SIMD Merkle — hash functions for commitment verification
ADR-013: ZK Execution Proofs — Groth16 circuit patterns reused
ADR-030: Federated Constellation Governance — reputation system for dropout handling
ADR-033: Space-Grade Self-Learning — base federation protocol extended here
TDD Reference
TDD v5.1: Base terrestrial architecture
TDD v5.2 Space Computing Extension, Part S4.5: Privacy-Preserving Federation integration
