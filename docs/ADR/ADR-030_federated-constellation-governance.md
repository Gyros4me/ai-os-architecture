# ADR-030: Federated Constellation Governance

**Status:** Proposed  
**Date:** 2026-02-26  
**Authors:** Alessandro La Gamba  
**Deciders:** Architecture team  

---

## Context

0xMeridian v5.1 is designed as a single-node AI OS. However, objectives that exceed a single node's compute envelope or data access — climate simulations, continental logistics, AGI safety research, global financial clearing — require coordination across multiple sovereign AI OS instances.

The coordination problem has three conflicting requirements:

1. **Sovereignty:** each node owner (human, enterprise, institution) must retain absolute control over their data and must be able to exit the constellation without data exposure
2. **Verifiability:** a node that claims to have completed a subtask must prove it mathematically — trust-based assertions are insufficient for financial, medical, and regulatory use cases
3. **No single point of failure:** a centralised orchestrator (Kubernetes control plane, cloud coordinator) defeats sovereignty and creates a SPOF

Existing solutions — federated learning frameworks (PySyft, Flower), cloud orchestrators (Kubernetes), blockchain smart contracts — each solve one or two of these requirements but not all three simultaneously.

---

## Decision

**Implement a Federation Layer (Layer 6) above the single-node kernel, based on Ambassador Agents, ZK-verified Service Level Agreements (ZK-SLAs), and a rotative Raft consensus among ambassadors. The constellation does not ask for trust — it asks for proofs.**

```
┌─────────────────────────────────────────────────────────────┐
│                    CONSTELLATION LAYER                      │
│                                                             │
│  ┌──────────────┐   BUS 4 (gRPC mTLS + WireGuard Mesh)     │
│  │  Ambassador  │◄─────────────────────────────────────►   │
│  │  Agent       │   ZK-SLA proofs · metadata · cred.settle │
│  │  (OCaml)     │                                           │
│  └──────┬───────┘                                           │
│         │ Bus 1/2/3 (internal only)                        │
├─────────▼───────────────────────────────────────────────────┤
│                  AI OS KERNEL (single node)                 │
│  Rust kernel · Magellano · Agent Swarm · 3 Buses            │
└─────────────────────────────────────────────────────────────┘
```

### Core Components

#### 1. Ambassador Agent

```ocaml
(* agents/ambassador/src/ambassador.ml *)

type constellation_node = {
  node_id:      string;         (* DID: did:aios:sha256:... *)
  pub_key:      Ed25519.pubkey; (* Hardware-bound identity *)
  capabilities: capability list;
  reputation:   float;          (* 0.0–1.0, updated by ZK-SLA outcomes *)
}

type task_contract = {
  task_id:      string;
  description:  string;
  budget:       credits;
  deadline_ms:  int;
  verifier:     zk_circuit_id;  (* Which circuit verifies correct execution *)
  privacy:      [`DataStaysLocal | `HashOnly | `CiphertextOk];
}

(* Main negotiation loop *)
let negotiate_task (contract: task_contract) (candidates: constellation_node list)
    : (constellation_node * assignment) option =
  candidates
  |> List.filter (fun n -> n.reputation > 0.7)
  |> List.filter (fun n -> has_capability n contract.verifier)
  |> List.sort_by (fun n -> n.reputation)  (* prefer high-reputation nodes *)
  |> List.head_opt
  |> Option.map (fun winner ->
       let assignment = {
         assignee  = winner.node_id;
         contract  = contract;
         escrow    = lock_credits contract.budget;  (* credits held until proof submitted *)
       } in
       (winner, assignment)
     )
```

#### 2. Bus 4 — Inter-OS Fabric

Bus 4 extends the local 3-Bus architecture across network boundaries. It carries **only**:
- Task metadata (not payloads)
- ZK-proof objects (192 bytes each)
- Gradient ciphertexts (federated learning, homomorphically encrypted)
- Credit settlement transactions (Merkle-settled, ZK-verified)

```
BUS 4 PROTOCOL STACK
─────────────────────
L4: ZK Verification    │ Groth16/Plonk proof check before accepting any result
L3: Orchestration      │ OCaml Strategic Router (sync vs async routing decision)
L2: Signaling          │ gRPC mTLS (sync) + NATS JetStream (async) + WireGuard
L1: Identity           │ DID (Ed25519 hardware key) + mTLS, no central CA
```

Latency target: **< 50 ms** for ZK-SLA handshake (task assignment + proof submission acknowledgment).

#### 3. ZK-SLA (Zero-Knowledge Service Level Agreement)

Every subtask in the constellation is governed by a ZK-SLA:

```
ZK-SLA Lifecycle
────────────────
1. PROPOSE    Owner signs TaskContract, broadcasts to constellation via Gossip
2. ACCEPT     Winning node locks escrow credits; begins execution
3. EXECUTE    Node runs subtask locally; accumulates execution witnesses
4. PROVE      ZkProver generates ExecutionProof (Groth16, 192 bytes)
              public_inputs:  {task_id, result_hash, timestamp}
              private_inputs: {raw_data, intermediate_states}  ← never leaves node
5. SUBMIT     Ambassador sends {proof, result_hash} over Bus 4
6. VERIFY     Constellation Raft verifies: e(A,B) = e(α,β)·e(Σxᵢwᵢ,γ)·e(C,δ)
7a. VALID     Credits released from escrow to executing node; reputation +0.01
7b. INVALID   Credits slashed (returned to requester); reputation −0.1; circuit_id banned
```

#### 4. Service Definition Layer (SDL)

```idris
-- sdl/ConstellationService.idr

||| A service contract that can be decomposed into independently
||| verifiable subtasks. The type system ensures every subtask
||| has a corresponding ZK circuit before the service can be accepted.
record ServiceContract where
  constructor MkService
  service_id    : String
  subtasks      : List (task : SubTask ** ZkCircuit task.verifier_id)
  privacy_policy : PrivacyPolicy
  budget        : Credits
  deadline      : POSIXTime
```

#### 5. Constellation Consensus (Rotative Raft)

```
Leader election: highest (reputation × battery_pct × uptime) score wins
Raft cluster:    3–7 Ambassador Agents (odd number for quorum)
Log entries:     ZK-SLA outcomes, credit settlements, node join/leave
Gossip:          Membership, health, capability propagation (SWIM, ADR-004)
Epoch rotation:  Leader rotates every 10 min OR on leader failure (<500 ms)
```

#### 6. Distributed Credit Clearing

```
Every 100 ms:
  1. Collect batch of ZK-SLA outcomes (valid/invalid proofs)
  2. Build Merkle tree of batch (SIMD SHA256, ADR-011)
  3. Raft commit: Merkle root + settlement deltas
  4. Ambassador updates local wallet balances (OCaml STM)
  5. ZK proof of clearing correctness transmitted to all nodes
```

---

## Rationale

**Why ZK-proofs (not trusted execution environments — TEE):**  
TEEs (Intel SGX, ARM TrustZone) require hardware attestation chains that create centralized trust anchors. A ZK-proof is verified by anyone with the verifying key — no Intel or ARM required, no vendor lock-in, no attestation service SPOF.

**Why rotative Raft (not static leader):**  
A static leader is a SPOF and a privilege target. Rotating leadership every 10 minutes limits the blast radius of a compromised leader and distributes computational overhead.

**Why reputation scores (not stake-based admission):**  
Stake-based systems (cryptocurrency staking) introduce real economic incentives that can be gamed or manipulated externally. Reputation scores are internal, non-transferable, and reflect actual performance history — a node cannot buy reputation, only earn it.

**Why Bus 4 carries only metadata/proofs (not raw data):**  
Privacy-by-design: if raw data never traverses Bus 4, a network interception reveals nothing. The only thing transmitted is a 192-byte proof that the data was processed correctly. This enables GDPR Article 5 (data minimisation) compliance at the transport layer.

**Why Ambassador Agent in OCaml (not Rust):**  
The Ambassador's logic is heavily functional: negotiation trees, reputation scoring, contract matching. OCaml's algebraic types and pattern matching express these cleanly with formal guarantees (ADR-029 contracts are written in Idris 2 but the extracted implementation runs as OCaml). Rust is reserved for the security-critical verification layer (ZK verifier, WireGuard, ring-0 override).

---

## Rollout Phases

| Phase | Scope | Deliverable | Timeline |
|-------|-------|-------------|----------|
| 1 | Bus 4 protocol definition | gRPC schema, WireGuard config, DID format | Sprint 5–6 |
| 2 | ZK-SLA circuits (simple) | Inference verification circuit (ADR-013 extended) | Sprint 7–8 |
| 3 | 100-node simulation | Virtual nodes on localhost, full constellation protocol | Sprint 9–10 |
| 4 | Real pilot | 3–5 partner nodes (university labs + enterprise) | Sprint 11–12 |

---

## Consequences

**Positive:**
- Enables use cases impossible on a single node: multi-hospital federated learning, continental logistics, AGI safety research across institutions
- Privacy is a protocol guarantee, not a policy: raw data mathematically cannot leave the node
- No central point of failure: any Ambassador can become leader; any node can leave without affecting others
- Regulatory compliance: ZK-SLA audit trail satisfies MiFID II, MDR, and EU AI Act traceability requirements without exposing sensitive data

**Negative / Mitigations:**
- **ZK proving time (100–500 ms per subtask):** adds latency for tasks requiring proof before result is accepted → *mitigated by async ZK proving: result is transmitted immediately, proof follows within 500 ms; escrow holds credits until proof arrives*
- **Gossip convergence time (2–5 s for 10K nodes):** new nodes are not immediately visible to all other nodes → *mitigated by Bootstrap Protocol: new node connects to 5 seed nodes; functional within 500 ms even before full convergence*
- **Raft cluster size limit (7 nodes):** practical Raft limit means the full 10K-node constellation is not in a single Raft group → *resolved by hierarchical Raft: each geographic zone elects a 3-node Raft group; zone leaders form a meta-Raft for global decisions*
- **ZK circuit development cost:** a new task type requires a new ZK circuit (~2–4 weeks engineering) → *mitigated by circuit library: pre-built circuits for the 10 most common task patterns (inference, gradient aggregation, data transformation, merkle verification, threshold authorisation)*

---

## Alternatives Rejected

| Alternative | Reason rejected |
|-------------|----------------|
| Kubernetes multi-cluster | Centralised control plane defeats sovereignty; etcd is a SPOF; no ZK verification |
| Blockchain smart contracts (Ethereum) | 12–15 s block time too slow for real-time task markets; gas costs unpredictable; not embeddable |
| PySyft / Flower (federated learning) | Covers only ML training, not general task coordination; no ZK verification; Python-only |
| Secure Multi-Party Computation (MPC) only | Correct but 100–1000× slower than ZK for the same privacy guarantees; impractical for real-time tasks |
| Central clearinghouse | SPOF; requires trust in the clearinghouse operator; violates sovereignty requirement |

---

## Related

- ADR-004: Gossip+Raft — constellation uses SWIM gossip for membership and Raft for ZK-SLA consensus
- ADR-009: Idris 2 Specs — SDL service contracts are specified in Idris 2
- ADR-012: WireGuard Mesh — Bus 4 transport layer
- ADR-013: ZK Execution Proofs — the proving/verification protocol used for ZK-SLAs
- ADR-025: Energy Governance — Ambassador suspends constellation participation in PowerSave mode
- ADR-026: Human Override — override propagates to all constellation nodes via Bus 4 when action = NetworkIsolate
- ADR-027: Semantic Agent Versioning — Ambassador exchanges adapter manifests to negotiate task compatibility
- TDD v5.1, Parte J: Constellation Architecture (full sequence diagrams and Protobuf schemas)

---

## Responding to "This is just a blockchain"

A blockchain is a specific data structure (linked hash chain) with specific consensus (PoW or PoS) and specific properties (permissionless, immutable ledger). The constellation is:

- **Permissioned** — nodes must be explicitly admitted via cryptographic handshake
- **Not a ledger** — the Merkle-settled credit clearing is a *batch settlement mechanism*, not a transaction history
- **Not sequential** — tasks execute in parallel; only ZK-SLA outcomes are sequenced via Raft
- **Latency-optimised** — 100 ms settlement vs Ethereum's 12–15 s blocks
- **Embeddable** — runs inside the AI OS kernel, not as a separate network daemon

The constellation borrows ZK-proofs and Merkle trees from blockchain research but is not a blockchain.
