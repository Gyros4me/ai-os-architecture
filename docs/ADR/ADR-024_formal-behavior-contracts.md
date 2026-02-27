# ADR-024: Formal Behavior Contracts (Idris 2 / Granule)

**Status:** Proposed (v5.2)  
**Date:** 2026-02-26  
**Authors:** Alessandro La Gamba  
**Deciders:** Architecture team  

---

## Context

ADR-009 establishes formal security *specifications* for agent capabilities. ADR-024 extends this to full behavioral *contracts*: the complete set of pre/post-conditions, invariants, and resource linearity constraints that govern an agent's observable behavior.

The distinction:
- **ADR-009:** "This agent is only allowed to use these capabilities" (access control)
- **ADR-024:** "Before this agent runs, conditions X must hold. After it runs, properties Y are guaranteed. Resources Z are consumed exactly once." (behavioral contract)

The motivation comes from regulatory requirements and operational safety:
- **EU AI Act Art. 9:** High-risk AI systems must have risk management systems with documented behavioral guarantees
- **MDR (Medical Device Regulation):** Surgical assistance agents must never recommend an action without complete vital sign data
- **Financial compliance:** Transaction agents must never execute a transfer above threshold without dual authorization

Runtime checks (assertions, RBAC) can be bypassed by injection attacks. We need guarantees that hold at compile time — before any code runs.

Three approaches were evaluated:
- **Option A:** Runtime assertions + extensive testing
- **Option B:** OCaml module signatures (structural typing)
- **Option C:** Idris 2 dependent type contracts + Granule linear type resource tracking

---

## Decision

**Formal behavior contracts using two complementary tools:**
- **Idris 2:** Pre/post-conditions, invariants, safety predicates (dependent types, total functions)
- **Granule:** Resource linearity constraints (consume exactly once, no duplication, no dropping)

**Enforcement:** Rust kernel verifies proof objects at load time. No valid contract proof → agent not scheduled (same enforcement mechanism as ADR-009).

```
┌─────────────────────────────────────────────────────────────────┐
│              BEHAVIORAL CONTRACT SPECIFICATION                   │
│                                                                  │
│  Contract Layer 1: Preconditions (Idris 2)                       │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  "Agent may only execute if: vital_signs.complete = True  │   │
│  │   AND patient.consent = Signed AND session.authenticated"│   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  Contract Layer 2: Postconditions (Idris 2)                      │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  "After execution: output.contains_recommendation →       │   │
│  │   output.rationale.length > 0 AND output.confidence > 0.7│   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  Contract Layer 3: Resource Linearity (Granule)                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  "authorization_token : Authorization [1]                 │   │
│  │   (must be consumed exactly once — cannot be reused)"    │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### Idris 2 Contract: Diagnostic Agent

```idris
-- Precondition type: all required fields must be present
DiagnosticPrecondition : (session : AgentSession) → Type
DiagnosticPrecondition session =
  ( IsComplete session.vital_signs    -- all 6 vitals present
  × HasConsent session.patient.id     -- signed consent on file
  × IsAuthenticated session.operator  -- MFA-verified clinician
  )

-- Postcondition type: recommendations require complete rationale
DiagnosticPostcondition : (input : DiagnosticInput) → (output : DiagnosticOutput) → Type
DiagnosticPostcondition input output =
  ( output.recommendation = Some rec →
      ( rec.confidence_score > 0.7
      × rec.supporting_evidence.length >= 3
      × rec.contraindications_checked = True
      )
  )

-- The contract: a proof that the implementation satisfies both conditions
DiagnosticContract : Type
DiagnosticContract =
  ( pre  : DiagnosticPrecondition
  × post : DiagnosticPostcondition
  × impl : DiagnosticImpl pre post  -- implementation parameterized by proofs
  )
```

### Granule Contract: Authorization Token

```granule
-- Authorization token: linear type — consumed exactly once
-- Cannot be duplicated (no double-spend) or dropped (no silent failure)

transaction : Authorization [1] →  -- consumes the token exactly once
              TransactionRequest →
              Either TransactionError TransactionResult
transaction auth req =
  -- Granule's type system ensures 'auth' cannot appear more than once
  -- in the function body. The compiler rejects: use auth twice, or
  -- return without consuming auth.
  validateAndExecute auth req
```

### Haskell Planner Fallback Contract

ADR-007 specifies that the Haskell Planner falls back to OCaml on circuit breaker. ADR-024 ensures this fallback preserves the behavioral contract:

```idris
-- The fallback OCaml planner must satisfy the same behavioral contract
-- as the Haskell planner — proven at compile time
FallbackContractPreservation : Type
FallbackContractPreservation =
  (input : PlannerInput) →
  (haskell_contract : PlannerContract HaskellImpl) →
  (ocaml_contract   : PlannerContract OCamlImpl) →
  PlannerOutput HaskellImpl input ≡ PlannerOutput OCamlImpl input
-- ≡ is propositional equality — the fallback produces equivalent outputs
```

---

## Rationale

### Why dependent types (not just assertions)

Runtime assertions are evaluated at execution time — too late for safety-critical systems. If a surgical agent receives incomplete vital signs, a runtime assertion fires *after* the agent has already started execution. A dependent type contract prevents the agent from being called at all if the precondition is not satisfied — the type checker proves this at compile time.

### Why Granule for resources

Linear type systems (Granule, Rust ownership) provide the only way to prove that a resource is used exactly once. For authorization tokens, cryptographic keys, and single-use consent records, the property "cannot be reused" is essential for security — and cannot be proven by logic-based contracts alone.

### Why a separate ADR from ADR-009

ADR-009 addresses *capability* constraints (what an agent is allowed to access). ADR-024 addresses *behavioral* contracts (what an agent promises to do, regardless of its capabilities). A logging agent has no sensitive capabilities (ADR-009) but its behavioral contract might still specify: "always flush to disk within 1 second of receiving a record."

---

## Consequences

**Positive:**
- Surgical and financial agents have compile-time guarantees — not just tests
- Regulatory audit: contract proofs are machine-verifiable artifacts, not documents
- Fallback contracts ensure behavior is preserved during circuit breaker transitions

**Negative / Mitigations:**
- **Idris 2 expertise required:** Most engineers know neither dependent types nor Granule → *mitigated by contract template library covering 10 standard patterns; engineers fill in domain-specific predicates*
- **Tooling maturity:** Idris 2 IDE support and Granule are not at the level of mainstream languages → *contracts are written by a dedicated security team; not required of all developers*
- **Contract verification adds ~50ms to agent load time:** → *done once at load, not per-request; amortized over agent lifetime*

---

## Alternatives Rejected

| Alternative | Reason rejected |
|-------------|----------------|
| Runtime assertions only | Evaluated too late; injectable; no regulatory audit value |
| OCaml module signatures | Structural typing does not express pre/post-conditions or resource linearity |
| Rust borrow checker | Linear types for memory safety only; cannot express domain invariants (vital signs completeness) |
| TLA+ specifications | Protocol-level liveness/safety; not type-level behavioral contracts |
| Property-based testing | Covers known cases; cannot exhaustively prove absence of contract violation |

---

## Related

- ADR-009: Idris 2 Security Specs — foundational; this ADR extends to full behavioral contracts
- ADR-007: Circuit Breaker — fallback contract preservation is a key requirement
- ADR-026: Cryptographic Human Override — override mechanism has a contract: "can only be invoked by the authorized keyholding human"
- TDD v5.1, Parte I: Compliance — EU AI Act Art. 9, MDR, MiFID II contract examples
