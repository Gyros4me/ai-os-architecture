# ADR-029: Formal Behavior Contracts

**Status:** Proposed  
**Date:** 2026-02-26  
**Authors:** Alessandro La Gamba  
**Deciders:** Architecture team  

---

## Context

As agent autonomy increases, so does the risk of emergent unsafe behaviours. Runtime assertions and unit tests catch specific cases but cannot prove general properties: "this agent will *never* send data outside the network perimeter", "this agent will *always* require dual authorisation for transactions above €10K", "this agent *cannot* suggest a drug combination if blood pressure data is missing".

These are not bugs — they are invariants that must hold for *all* inputs, including adversarial ones crafted via prompt injection. Testing cannot prove universal properties; only formal verification can.

The gap identified in TDD v5.1 (GAP-09, partially resolved by ADR-009) is that security specs exist but are not systematically propagated into runtime enforcement. An agent can be formally verified at compile time and still receive a runtime task that violates its spec if the scheduling layer does not check compatibility.

---

## Decision

**Agents operating in high-risk categories carry Formal Behavior Contracts expressed in Idris 2 (dependent types) or Granule (linear types for resource constraints). The Rust Kernel Verifier checks the compiled proof object against the runtime task specification before scheduling. No contract → no scheduling for high-risk agents.**

### Risk Classification

| Risk Level | Contract Language | Enforcement Point | Examples |
|------------|------------------|-------------------|---------|
| **Critical** | Idris 2 — full dependent types, proof-carrying code | Pre-schedule kernel check (ring-0) | Key management, financial transactions > threshold, drug recommendations, autonomous actuation |
| **High** | Idris 2 spec + OCaml runtime assertions | Pre-execution + runtime checks | External API calls, database writes, cross-tenant data access |
| **Medium** | OCaml property-based tests (Crowbar) | CI/CD gate only | RAG retrieval, analytics, report generation |
| **Low** | Standard Rust/OCaml unit tests | CI/CD gate only | Logging, formatting, UI rendering |

### Idris 2 Contract — Example: Transaction Agent

```idris
-- contracts/transaction_agent.idr

module TransactionAgent

import Data.Fin
import Crypto.Ed25519

||| A transaction that has been authorised by the required number of principals.
||| The type parameter carries the authorisation count as a compile-time proof.
data AuthorisedTx : (required_sigs : Nat) -> Type where
  SingleAuth  : Ed25519Sig -> AuthorisedTx 1
  DoubleAuth  : Ed25519Sig -> Ed25519Sig -> AuthorisedTx 2

||| Submit a transaction. The type system enforces that high-value transactions
||| require double authorisation — this is a compile-time guarantee, not a
||| runtime check that can be bypassed.
submitTransaction :
  (amount : Double) ->
  (tx     : AuthorisedTx (if amount > 10000.0 then 2 else 1)) ->
  IO TxResult
submitTransaction amount tx = ...
-- Any call with amount > 10000 that provides only SingleAuth
-- will FAIL TO COMPILE — the invariant is enforced by the type checker.
```

The compiled proof object (`.proof` file) is embedded in the agent manifest:

```json
{
  "agent_id":     "transaction-agent",
  "risk_level":   "critical",
  "contract":     "TransactionAgent.idr",
  "proof_hash":   "sha256:4f7a...",
  "proof_object": "base64:...",   // Idris 2 compiled proof
  "properties": [
    "no_tx_above_10k_without_double_auth",
    "no_external_network_access",
    "all_amounts_non_negative"
  ]
}
```

### Granule Contract — Example: GDPR Data Agent

```granule
-- contracts/gdpr_data_agent.gr
-- Granule's linear types ensure data is consumed exactly once
-- and never duplicated without explicit policy approval.

import Linear

-- Patient record is a linear resource: it can be used exactly once.
-- Attempting to use it twice is a compile-time error.
processPatientRecord : PatientRecord ⊸ ConsentToken ⊸ AnonResult
processPatientRecord record consent =
  -- record is consumed here; it cannot be passed to a logging function
  -- without going through the anonymisation step first
  let anon = anonymise record consent
  in AnonResult anon
-- Proof: patient data cannot be duplicated or leaked without
-- an explicit copy operation, which requires an additional ConsentToken.
```

### Kernel Verifier

```rust
// kernel/src/contracts/verifier.rs

pub fn pre_schedule_check(
    agent_manifest: &AgentManifest,
    task_spec:      &TaskSpec,
) -> ScheduleDecision {

    // 1. Risk classification determines enforcement level
    if agent_manifest.risk_level < RiskLevel::High {
        return ScheduleDecision::Approve; // no contract required for low/medium
    }

    // 2. Proof object must be present and signed
    let proof = match &agent_manifest.proof_object {
        Some(p) => p,
        None    => return ScheduleDecision::Reject("missing proof object for high-risk agent"),
    };

    // 3. Verify proof object signature (Critic Agent signed it)
    if !verify_ed25519(&proof.signature, &proof.canonical_bytes()) {
        return ScheduleDecision::Reject("invalid proof object signature");
    }

    // 4. Check task_spec satisfies the declared properties
    for property in &agent_manifest.properties {
        if !task_spec.satisfies(property) {
            return ScheduleDecision::Reject(
                &format!("task violates contract property: {}", property)
            );
        }
    }

    ScheduleDecision::Approve
}
```

---

## Rationale

**Why Idris 2 (not Coq, Lean, Agda):**  
- Idris 2 has first-class linear types (QTT — Quantitative Type Theory), making it the only mainstream dependently-typed language that can also express resource linearity (critical for GDPR data flow proofs)
- Idris 2's `--extract` flag generates OCaml code, providing a direct path from spec to runnable implementation
- The team already uses OCaml (ADR-001); the toolchain overlap reduces operational complexity

**Why Granule for resource contracts:**  
Granule's graded modal types provide finer-grained resource tracking than Idris 2's linear types. For GDPR/HIPAA data flow proofs ("this data is used at most once without consent renewal"), Granule's type system is more expressive than Idris 2's `%linear` annotation.

**Why kernel-level enforcement (not agent-level self-assertion):**  
An agent asserting its own contract at runtime is equivalent to a prisoner self-reporting their prison escape. The enforcement point must be external to the agent — the Kernel Verifier runs before the agent's code receives the task.

**Why proof objects (not runtime constraint solvers):**  
Runtime constraint solvers (e.g., Z3 SMT) can prove properties for specific inputs but are too slow (100 ms–10 s per call) for pre-schedule checks. Proof objects are computed once at build/training time and verified in microseconds at runtime.

---

## Consequences

**Positive:**
- Universal safety properties are guaranteed by the type system, not by test coverage
- Prompt injection cannot bypass a contract: even if an adversary crafts a task that looks like a legitimate request, it will fail the `task_spec.satisfies(property)` check if it violates a formal property
- MDR and EU AI Act compliance: formal proofs are the strongest possible evidence of safety property compliance
- Refactoring safety: changing an agent's implementation cannot accidentally remove a safety property without breaking the proof

**Negative / Mitigations:**
- **Idris 2 learning curve:** significant for developers unfamiliar with dependent types → *mitigated by providing contract templates for the 5 most common high-risk patterns (financial threshold, data flow, network isolation, resource linearity, dual authorisation)*
- **Proof object generation time:** ~10–30 min per agent for complex contracts → *occurs at build time / training time, not at runtime; acceptable for the deployment pipeline*
- **Specification–implementation gap:** a correct proof of the Idris 2 spec does not guarantee the OCaml implementation matches the spec → *mitigated by using Idris 2's `--extract` to generate OCaml directly from the spec where feasible*
- **Medium/low risk agents uncovered:** property-based tests are not formal proofs → *explicitly accepted; the cost–benefit of full formal verification for logging agents is not justified*

---

## Alternatives Rejected

| Alternative | Reason rejected |
|-------------|----------------|
| Runtime assertions only | Cannot prove universal properties; adversarial inputs can bypass specific assertion conditions |
| TLA+/PlusCal specs | No executable extraction path; verification and implementation are separate artefacts that can diverge |
| Coq | No linear types; extraction to OCaml requires proof engineering overhead; larger community but worse toolchain fit |
| SMT solvers (Z3) at runtime | Too slow for pre-schedule check (100ms+); path coverage incomplete for LLM-generated task specs |
| Policy-as-code (OPA/Rego) | Declarative rules, not proofs; cannot express dependent-type properties; bypassable by crafted inputs |

---

## Related

- ADR-009: Idris 2 Specs + OCaml Security — this ADR extends ADR-009 from compile-time specs to runtime kernel enforcement
- ADR-026: Human Override — critical agents with proof objects still yield to the cryptographic override
- ADR-027: Semantic Agent Versioning — proof object hash is included in the adapter manifest; a new training run that changes a property requires a new proof
- ADR-002: Agent-per-Resource — Tier 3 micro-agents are too lightweight for formal contracts; contracts apply to Tier 1 and 2 agents only
- TDD v5.1, Parte H: Security Threat Model — formal contracts address Threat T-04 (Prompt Injection leading to policy bypass)
