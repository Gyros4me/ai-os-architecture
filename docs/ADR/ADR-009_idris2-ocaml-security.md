# ADR-009: Idris 2 Specs + OCaml Implementation for Security

**Status:** Accepted  
**Date:** 2026-02-17  
**Authors:** Alessandro La Gamba  
**Deciders:** Architecture team  

---

## Context

Security-critical agent behaviors (access to private keys, financial transactions, medical data, personal information) must be provably correct — not just tested. Runtime checks can be bypassed (injection attacks, logic bugs). Unit tests cover known scenarios, not the full state space.

Two distinct problems exist:

1. **Capability whitelisting:** An agent should only be able to call the functions its design permits. A Logging Agent must never be able to initiate a network connection.
2. **Data flow constraints:** Sensitive data must not leave the system unencrypted or without consent. These properties must hold across all possible execution paths, not just tested ones.

Standard approaches evaluated:
- **Option A:** Runtime policy enforcement (RBAC, OPA, capabilities at runtime)
- **Option B:** Static analysis (linters, type checkers on OCaml/Rust)
- **Option C:** Formal specifications (Idris 2 dependent types) with extracted or manually-aligned implementations

---

## Decision

**Security specifications written in Idris 2 (dependent types, total functions). Implementations in OCaml (aligned manually or extracted). Rust kernel loads proof objects and verifies them against system policy before scheduling high-risk agents.**

```
┌─────────────────────────────────────────────────────────────────┐
│                FORMAL VERIFICATION PIPELINE                     │
│                                                                 │
│  Specification (Idris 2)                                        │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  AgentCapabilities : Type                                 │  │
│  │  SecurityPolicy    : Type                                 │  │
│  │  DataFlowProof     : (agent : Agent) → (policy : Policy)  │  │
│  │                    → Type                                 │  │
│  └──────────────────────────┬────────────────────────────────┘  │
│                             │ compile                           │
│                             ▼                                   │
│  Proof Objects (.ibc bytecode)                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Compiled evidence that spec is satisfied                 │  │
│  │  Embedded in agent bundle at build time                   │  │
│  └──────────────────────────┬────────────────────────────────┘  │
│                             │ load                              │
│                             ▼                                   │
│  Rust Kernel Verifier                                           │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  fn verify_agent_proof(bundle: &AgentBundle)              │  │
│  │      → Result<SchedulePermit, SecurityViolation>          │  │
│  │  // No proof → no schedule. Always.                       │  │
│  └───────────────────────────────────────────────────────────┘  │
│                             │ permit                            │
│                             ▼                                   │
│  OCaml Implementation                                           │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Runtime-aligned with Idris spec                          │  │
│  │  Property tests via Crowbar/QCheck                        │  │
│  │  Runtime assertions for invariants not in type system     │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### Idris 2 Capability Model (excerpt)

```idris
-- Capability type: what an agent is allowed to do
data Capability
  = NetworkRead    -- may read from network
  | NetworkWrite   -- may write to network
  | StorageRead    -- may read local storage
  | StorageWrite   -- may write local storage
  | KeyAccess      -- may access cryptographic keys
  | ExternalTool   -- may invoke external tools
  | PersonalData   -- may handle PII

-- Proof that an agent's implementation respects its declared capabilities
AgentPolicy : (declared : List Capability) → (actual : AgentImpl) → Type
AgentPolicy declared impl =
  -- For all execution paths in impl, the capabilities used are a subset of declared
  (path : ExecPath impl) → usedCapabilities path `subsetOf` declared

-- Transaction Agent policy: network + storage, no key access without authorization
TransactionAgentPolicy : Type
TransactionAgentPolicy =
  AgentPolicy
    [NetworkRead, NetworkWrite, StorageRead, StorageWrite]
    TransactionAgentImpl

-- Proof (must be provided at build time):
transactionAgentProof : TransactionAgentPolicy
transactionAgentProof = ... -- type-checked by Idris 2 compiler
```

### Property Tests (OCaml, Crowbar)

```ocaml
(* Property: Memory Agent never writes PII to external storage *)
let pii_never_external = Crowbar.add_test
  ~name:"memory_agent_pii_isolation"
  [Crowbar.bytes; Crowbar.bytes] (* random input, random PII *)
  (fun input pii ->
    let state = MemoryAgent.init () in
    let _ = MemoryAgent.process state ~input ~pii in
    (* Invariant: after any operation, no PII in external_writes *)
    assert (List.for_all
      (fun write -> not (contains_pii write pii))
      (MemoryAgent.external_writes state)))
```

### Rust Kernel Verifier

```rust
/// Called before scheduling any agent marked `SecurityLevel::High`
pub fn verify_agent_proof(bundle: &AgentBundle) -> Result<SchedulePermit, SecurityViolation> {
    let proof = bundle.security_proof.as_ref()
        .ok_or(SecurityViolation::MissingProof { agent_id: bundle.id })?;

    // Deserialize Idris 2 proof object
    let proof_obj = IdrisProof::deserialize(proof)
        .map_err(|e| SecurityViolation::MalformedProof { agent_id: bundle.id, error: e })?;

    // Check against system-wide security policy
    let system_policy = self.security_policy.read();
    proof_obj.verify_against(&system_policy)
        .map_err(|e| SecurityViolation::PolicyViolation { agent_id: bundle.id, violation: e })?;

    Ok(SchedulePermit { agent_id: bundle.id, valid_until: Instant::now() + Duration::from_secs(3600) })
}
```

---

## Rationale

### Why Idris 2 for specifications

Idris 2 is the most mature language for **proof-carrying code** in the functional ecosystem:
- **Dependent types** allow expressing properties like "this function never returns null" or "the output list has the same length as the input" at the type level
- **Total functions** (checked by the elaborator) prevent infinite loops and partial functions from existing in security-critical specs
- **Universe levels** allow reasoning about proofs of proofs (needed for composition of security properties)

Alternative formal methods tools (TLA+, Alloy, Coq) were evaluated but rejected:
- **Coq:** Proof extraction to OCaml is supported but requires extensive tactic scripting; ecosystem is smaller
- **TLA+:** Not suited for type-level property specification; better for protocol-level liveness/safety
- **Alloy:** Bounded model checking only; cannot prove unbounded correctness

### Why OCaml for implementation (not Idris extraction)

Idris 2 can extract to Scheme or Erlang, but not directly to OCaml. Manual alignment is preferred because:
- OCaml has better performance characteristics for the agent runtime (GC tuning, Lwt async)
- Property-based testing with Crowbar/QCheck provides independent verification
- The team already has OCaml expertise; Idris is used only for specifications

### Why runtime proof verification (not compile-time only)

Agents are loaded dynamically (plugin model). A compromised agent binary could claim to have a proof without having one. The Rust kernel verifier re-checks the proof object on every load — preventing supply chain attacks where a legitimate proof is replaced by a forged one.

---

## Consequences

**Positive:**
- Mathematical guarantees for capability whitelisting — not just tests
- Proof objects are auditable artifacts — regulators can verify properties without seeing implementation
- Crowbar property tests exercise the full state space for properties not expressible in types
- Clear separation: specifications evolve independently of implementations

**Negative / Mitigations:**
- **Idris 2 expertise is rare:** Learning curve for security engineers → *mitigated by providing a spec template library for common patterns (no-network, no-PII, read-only storage)*
- **Proof object size (~50KB) adds to agent bundle:** → *acceptable; loaded once at schedule time, not per-request*
- **Not all properties are expressible in dependent types:** Timing-based side channels, hardware vulnerabilities → *out of scope for this ADR; covered by TDD v5.1 Parte H (Threat Model)*

---

## Alternatives Rejected

| Alternative | Reason rejected |
|-------------|----------------|
| RBAC at runtime (OPA/Casbin) | Turing-complete policy language → policy itself can have bugs; no mathematical proof |
| SELinux / AppArmor profiles | OS-level sandboxing without semantic understanding of agent behavior; no type-level guarantees |
| Rust type system only | Rust ownership prevents memory unsafety, not capability violations (a Rust program can still exfiltrate data) |
| Formal verification via Coq | Extraction to OCaml requires extensive tactic proofs; team expertise not present |
| No formal verification | Unacceptable for Medical (MDR), Finance (MiFID II), and Government (EU AI Act) compliance |

---

## Related

- ADR-024: Formal Behavior Contracts — extends this ADR with agent-level behavior contracts (not just capabilities)
- ADR-026: Cryptographic Human Override — the override mechanism itself has an Idris 2 proof: "override signal cannot be forged"
- TDD v5.1, Parte H: Security Threat Model — 10 threat scenarios, 4-layer prompt injection defense
- TDD v5.1, Parte I: Compliance — EU AI Act Art. 9, GDPR Art. 25, MDR mapping to formal proofs
