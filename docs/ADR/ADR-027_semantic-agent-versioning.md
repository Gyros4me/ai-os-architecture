# ADR-027: Semantic Agent Versioning

**Status:** Proposed  
**Date:** 2026-02-26  
**Authors:** Alessandro La Gamba  
**Deciders:** Architecture team  

---

## Context

The QLoRA nightly loop (ADR-008) means agent weights change daily. Standard software versioning (Git SHA, SemVer for code) was designed for deterministic, text-based artefacts. It does not capture:

1. **Behavioural drift** — a model trained on 50 new samples may change its refusal rate, tone, or reasoning style in ways that are invisible to a diff of the adapter weights
2. **Rollback semantics** — reverting to adapter `v1.4.2` must mean reverting to a specific, reproducible *behaviour*, not just a specific set of weights
3. **Regulatory auditability** — MDR (Medical Device Regulation), MiFID II, and EU AI Act require that every decision made by a high-risk AI system be traceable to a specific, documented model version with a record of what changed
4. **Compatibility contracts** — a Planner Agent trained with adapter `v2.1.0` may be incompatible with an Executor Agent expecting `v1.x` planning schemas

Git SHA of the adapter file answers "what bytes changed". It does not answer "how did the agent's behaviour change, and is it still safe to deploy?"

---

## Decision

**Every LoRA adapter produced by the QLoRA loop carries a signed `adapter_manifest.json` that declares behavioural changes alongside standard metrics. The Critic Agent generates the manifest; the Kernel Verifier checks it before hot-swap; the Registry stores the full history.**

### Manifest Schema

```json
{
  "schema_version":      "1.0",
  "agent_id":            "planner-core",
  "version":             "2.1.0",
  "base_model_id":       "magellano-3.3b-nf4",
  "adapter_hash":        "sha256:3f4a8c9d...",
  "training_data_hash":  "sha256:7b2e1f0a...",
  "parent_version":      "2.0.3",
  "created_at":          "2026-02-26T03:14:22Z",
  "training_samples":    87,
  "ab_test_score":       0.087,
  "ab_test_threshold":   0.050,

  "behavioral_changes": [
    {
      "type":        "improvement",
      "dimension":   "cyclic_dependency_reasoning",
      "delta":       "+14.2%",
      "description": "Correctly resolves DAGs with indirect cycles (A→B→C→A) in 97% of test cases vs 85% before"
    },
    {
      "type":        "safety_constraint_update",
      "dimension":   "refusal_rate",
      "delta":       "+2.1%",
      "description": "Refuses task decompositions that would exceed declared resource budgets. Breaking change for callers that relied on soft-limit override."
    }
  ],

  "compatibility": {
    "kernel_min":        "5.1.0",
    "executor_min":      "2.0.0",
    "breaking_changes":  true,
    "migration_notes":   "Callers using soft-limit override must set explicit budget exceptions via TaskSpec.budget_override"
  },

  "rollback_safe":        false,
  "rollback_reason":      "Safety constraint update changes refusal rate — rolling back re-enables previously-refused task patterns",

  "regulatory": {
    "mdr_class":          "IIb",
    "change_significance": "substantial",
    "requires_revalidation": true
  },

  "signature": {
    "principal":   "critic-agent@aios-node-7f3a",
    "algorithm":   "ed25519",
    "value":       "base64:aBcD..."
  }
}
```

### Versioning Convention

The version field follows a behavioural SemVer interpretation:

| Increment | Meaning | Example |
|-----------|---------|---------|
| **MAJOR** | Breaking behavioural change — a component relying on the previous behaviour must be updated | `1.x.x → 2.0.0`: Planner now requires explicit budget declarations |
| **MINOR** | New capability added, backward compatible | `2.0.x → 2.1.0`: Better cyclic dependency resolution |
| **PATCH** | Quantitative improvement, no behavioural interface change | `2.1.0 → 2.1.1`: +3% accuracy on existing capabilities |

### Critic Agent Manifest Generation

```haskell
-- agents/critic/src/ManifestGenerator.hs

generateManifest :: AdapterCandidate -> BaselineMetrics -> IO AdapterManifest
generateManifest candidate baseline = do
  behavioralDiff <- runBehavioralSuite candidate baseline
  let changes     = classifyChanges behavioralDiff
  let semverBump  = determineSemver changes
  let rollbackSafe = not (any isSafetyConstraintChange changes)
  let regulatory  = classifyRegulatorySignificance changes

  return AdapterManifest
    { version          = bumpVersion (adapterVersion candidate) semverBump
    , behaviorChanges  = changes
    , rollbackSafe     = rollbackSafe
    , regulatory       = regulatory
    , abTestScore      = abScore behavioralDiff
    , trainingDataHash = sha256 (trainingDataPath candidate)
    -- ... remaining fields
    }
```

### Kernel Verifier Integration

Before hot-swap (ADR-008 step 5), the Kernel Verifier checks:

```rust
// kernel/src/model_loader/verifier.rs

pub fn pre_swap_check(manifest: &AdapterManifest) -> SwapDecision {
    // 1. Signature valid?
    if !verify_ed25519(&manifest.signature, &manifest.canonical_bytes()) {
        return SwapDecision::Reject("invalid manifest signature");
    }

    // 2. Compatibility satisfied?
    if !KERNEL_VERSION.satisfies(&manifest.compatibility.kernel_min) {
        return SwapDecision::Reject("kernel version incompatible");
    }

    // 3. Breaking change without migration flag?
    if manifest.compatibility.breaking_changes
       && !manifest.has_migration_notes() {
        return SwapDecision::Reject("breaking change without migration notes");
    }

    // 4. Regulatory gate: substantial MDR change requires operator approval
    if manifest.regulatory.requires_revalidation {
        return SwapDecision::AwaitApproval(manifest.version.clone());
    }

    SwapDecision::Approve
}
```

---

## Rationale

**Why behavioural changes (not just loss metrics):**  
Loss metrics measure the model's fit to the training distribution. They do not measure what matters to operators: "does this agent still refuse dangerous requests?", "does it still produce valid Protobuf schemas?", "has its tone changed in a way that affects user trust?" A 0.02 drop in training loss is meaningless to a medical device regulator; a documented change in refusal rate is mandatory to disclose.

**Why a signed manifest (not unsigned JSON):**  
An unsigned manifest can be forged or accidentally overwritten. The Critic Agent's Ed25519 signature makes the manifest tamper-evident — the Kernel Verifier can prove that the manifest was produced by a specific, authorised Critic instance.

**Why behavioural SemVer (not weight-hash versioning):**  
Weight hashes identify uniqueness but not compatibility. SemVer MAJOR signals "this adapter changes the agent's external contract" — a piece of information no weight hash can convey. Downstream components (Executor, Interface Agent) need to know whether they must update their expectations, not whether the weights changed.

**Why `rollback_safe` flag:**  
Not all rollbacks are safe. An adapter that introduced a new safety constraint cannot be safely rolled back — doing so re-enables the previously-refused behaviour. The flag forces an explicit operator acknowledgment for unsafe rollbacks, preventing accidental regressions in safety properties.

---

## Consequences

**Positive:**
- Full regulatory traceability: every decision by a production agent is linked to a specific, documented adapter version with a behavioural changelog
- Debugging: "The system started refusing orders on March 15" → `git log --follow adapter_manifest.json | grep refusal_rate` immediately points to the culprit
- Safe rollback: the `rollback_safe` flag prevents accidental regression of safety constraints
- Cross-node compatibility: constellation nodes (ADR-030) can negotiate adapter compatibility before accepting a task

**Negative / Mitigations:**
- **Behavioural suite runtime:** running the full behavioural diff adds ~10 min to the nightly QLoRA cycle → *mitigated by running the suite in parallel on a dedicated CPU core; it does not block the training job*
- **Manifest size:** ~5 KB per adapter, ~365 per year per agent → 1.8 MB/year/agent → *negligible; stored in the Registry Agent's persistent tier*
- **False classification:** the Critic may mislabel a MAJOR change as MINOR → *mitigated by conservative classification rules: any change to refusal rate, output schema, or resource consumption is always MAJOR*
- **Regulatory bottleneck:** `requires_revalidation = true` blocks hot-swap until operator approves → *this is the intended behaviour; the bottleneck is the regulatory requirement, not the system design*

---

## Alternatives Rejected

| Alternative | Reason rejected |
|-------------|----------------|
| Git SHA only | Identifies a file, not a behaviour; no compatibility semantics |
| MLflow model registry | External dependency; no behavioural diff support; no kernel-level integration |
| Standard SemVer on code | Agents are not code releases; weight changes are not function signature changes |
| Unsigned manifest | Forgeable; provides false confidence in provenance |
| No versioning (always latest) | Incompatible with MDR, MiFID II, EU AI Act traceability requirements |

---

## Related

- ADR-008: QLoRA Feedback Loop — the training loop that triggers manifest generation
- ADR-009: Idris 2 Specs — formal proof that the manifest schema is complete for regulatory purposes
- ADR-026: Human Override — `requires_revalidation` adapters require the same approval channel as override signals
- ADR-030: Constellation Governance — Ambassador Agents exchange manifests to negotiate task compatibility across nodes
- TDD v5.1, Parte B.5: Model Loader — `VersionController` service that manages the adapter registry and manifest history
