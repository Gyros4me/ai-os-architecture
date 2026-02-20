# ADR-003: Magellano Default Engine vs Model-Agnostic

**Status:** Accepted  
**Date:** 2026-02-17  
**Authors:** Alessandro + Claude (CoS)  
**Deciders:** Architecture team  

---

## Context

Magellano (3.3B Mamba-MoE, Swift + Metal) is developed in-house and highly optimized for Apple Silicon. However, it has a hard context limit of 512 tokens and runs only on Apple platforms. The system must also handle:

- Long documents (>512 tokens) requiring larger context windows
- Non-Apple deployment targets (Linux servers, cloud)
- Tasks where quality requirements exceed Magellano's capabilities
- Battery-constrained scenarios requiring a smaller footprint model

Two positions were evaluated:
- **(A) Magellano-only:** Single model, maximum optimization, locked ecosystem
- **(B) Model-agnostic HAL:** Abstract backend layer, any model pluggable, Magellano as one option

---

## Decision

**Magellano as the default engine, with an Inference HAL (Hardware Abstraction Layer) that allows alternative backends. All requests route through the Model Router applying a configurable RoutingPolicy.**

```rust
/// InferenceBackend — the Rust trait every backend must implement (GAP-13)
pub trait InferenceBackend: Send + Sync {
    fn generate(&self, req: InferenceRequest) -> impl Future<Output = Result<InferenceResponse>>;
    fn embed(&self, texts: &[&str]) -> impl Future<Output = Result<Vec<Embedding>>>;
    fn max_context_tokens(&self) -> usize;
    fn estimated_latency_ms(&self) -> u64;
    fn is_available(&self) -> bool;
    fn backend_id(&self) -> &'static str;
    fn health_check(&self) -> impl Future<Output = BackendHealth>;
}
```

Zero coupling: no component outside the Model Router ever references a concrete backend. Magellano is instantiated as `Box<dyn InferenceBackend>` like any other backend.

---

## Default FallbackChain (RoutingPolicy)

The Model Router applies rules in priority order:

```
Priority 1 → Magellano 3.3B (local, Metal)
  Condition: input < 512 tokens AND running on Apple Silicon AND battery > 20%
  Latency: 50–100ms | Cost: $0 | Quality: high

Priority 2 → Magellano 77M (local, CPU)
  Condition: battery < 20% OR task_type == "trivial" (intent parsing, formatting)
  Latency: 200–400ms | Cost: $0 | Quality: medium

Priority 3 → llama.cpp GGUF Q4 (local, CPU)
  Condition: 512 < input_tokens < 4096
  Latency: 800ms–3s | Cost: $0 | Quality: medium-high

Priority 4 → Cloud API (Anthropic/OpenAI)
  Condition: input_tokens > 4096 OR task_type == "quality-critical"
  Latency: +200–500ms overhead | Cost: $/1M tokens | Quality: highest
```

---

## Rationale

**Why not Magellano-only:**
- Context limit of 512 tokens is too restrictive for document processing, long code analysis, and multi-turn reasoning chains
- Platform lock-in to Apple Silicon prevents any server-side or cloud deployment
- Single point of failure for the entire inference layer

**Why not fully model-agnostic (no default):**
- Magellano covers ~80% of typical task volume: intent parsing, code generation <512 tok, validation, embedding generation, summarization
- Optimized Metal kernels provide 8.81× speedup vs CPU — abandoning this advantage for "purity" has no engineering justification
- The FallbackChain means Magellano IS the default; the HAL just ensures graceful degradation for the other 20%

**Why this hybrid:**
- The `InferenceBackend` Rust trait (7 methods) decouples *completely* — the Planner Agent never imports anything from the `magellano` crate
- Routing logic is centralized in the Model Router — one place to tune, one place to monitor
- Each backend runs the same conformance test suite → guaranteed behavioral consistency

---

## Consequences

**Positive:**
- ~80% of tasks served locally at zero marginal cost
- Graceful degradation: if Magellano crashes, the system falls back automatically to llama.cpp then cloud
- Zero coupling: swapping Magellano for a new local model requires implementing the trait and updating RoutingPolicy — no other changes

**Negative / Mitigations:**
- **Partial Apple lock-in:** Magellano 3.3B still preferred → if non-Apple deployment grows, Priority 3/4 will carry more load → *mitigated by cloud fallback being always available*
- **Latency variability:** local→cloud switch adds +200–500ms → *mitigated by client-side timeout budgets and streaming responses*
- **Cloud API cost:** priority 4 has monetary cost → *mitigated by budget management alerts (see Observability, GAP-01)*
- **Conformance testing overhead:** every new backend must pass trait compliance tests → *this is a feature, not a bug*

---

## The HAL in the Architecture

```
                    ┌─────────────────┐
   Planner Agent ──►│   Model Router  │
   Executor Agent──►│  (RoutingPolicy)│
   Memory Agent ───►│                 │
                    └────────┬────────┘
                             │ Box<dyn InferenceBackend>
              ┌──────────────┼──────────────┬───────────────┐
              ▼              ▼              ▼               ▼
     ┌──────────────┐ ┌──────────┐ ┌────────────┐ ┌──────────────┐
     │ Magellano    │ │Magellano │ │ llama.cpp  │ │  Cloud API   │
     │ 3.3B (Metal) │ │ 77M(CPU) │ │  GGUF Q4   │ │ Anthropic/OAI│
     └──────────────┘ └──────────┘ └────────────┘ └──────────────┘
```

---

## Alternatives Rejected

| Alternative | Reason rejected |
|-------------|----------------|
| Model-agnostic pure (no default preference) | Loses Metal optimizations; 8.81× speedup abandoned without justification; Magellano TCO advantage wasted |
| Magellano-only | Context 512 too limiting; Apple-only; single point of failure for inference |
| Dynamic selection via LLM | Circular dependency: you can't use an LLM to decide which LLM to use |
| Runtime model voting | Latency unacceptable; adds complexity with no quality benefit over deterministic FallbackChain |

---

## Related

- ADR-001: Rust + Swift Polyglot (defines the C FFI boundary this trait crosses)
- GAP-13: `InferenceBackend` Rust trait — 7 methods, full specification in TDD v5.1 Parte B
- TDD v5.1, Parte B.3: Model Router implementation with 4 routing policies
- ADR-004: Gossip+Raft (the Consensus Agent uses the HAL for replan decisions)

---

## Responding to "Why not just use an OpenAI API wrapper?"

An API wrapper is a client library. The HAL is a kernel service. The difference:

1. **Routing is automatic** — no application code decides which model to call; the Model Router does, based on runtime conditions (battery, token count, latency budget, task type)
2. **Fallback is transparent** — if Magellano 3.3B OOMs at 3am, the system switches to llama.cpp without waking anyone up
3. **Metering is centralized** — all inference passes through one measurement point (cost, latency, quality score correlation)
4. **Backend swap requires zero application changes** — tomorrow's Magellano 13B replaces 3.3B by implementing the same 7-method trait
