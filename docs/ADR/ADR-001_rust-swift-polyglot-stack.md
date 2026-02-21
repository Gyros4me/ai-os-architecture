# ADR-001: Rust + Swift Polyglot Stack

**Status:** Accepted  
**Date:** 2026-02-17  
**Authors:** Alessandro La Gamba  
**Deciders:** Architecture team  

---

## Context

The AI OS requires two distinct execution environments that no single language satisfies simultaneously:

1. **Kernel level** — memory safety without GC, predictable latency, native async/await, mature systems ecosystem (gRPC, serialization, consensus)
2. **Inference level** — direct access to Metal GPU kernels on Apple Silicon for optimal performance, CoreML integration, ANE (Apple Neural Engine) access

Three options were evaluated:
- **Option A:** Monolanguage (Rust only)
- **Option B:** Polyglot (Rust + Swift)  
- **Option C:** Custom language

---

## Decision

**Stack polyglot: Rust for the kernel, Swift + Metal for Magellano, connected via C FFI.**

```
┌─────────────────────────────────┐   ┌─────────────────────────────────┐
│         RUST — KERNEL           │   │      SWIFT — MAGELLANO          │
│                                 │   │                                 │
│  tokio async/await              │   │  Metal kernel personalizzati    │
│  tonic gRPC                     │   │  Apple Silicon 8.81× speedup   │
│  serde serialization            │   │  NF4 quantization               │
│  openraft consensus             │   │  ANE / Neural Engine            │
│  zero-cost abstractions         │   │  CoreML integration             │
└──────────────┬──────────────────┘   └──────────────┬──────────────────┘
               │                                      │
               └──────────── C FFI bridge ────────────┘
                        (batch calls, negligible overhead)
```

---

## Rationale

**Why Rust for the kernel:**
- Memory safety without GC → no stop-the-world pauses, predictable latency for real-time orchestration
- Zero-cost abstractions → kernel overhead approaches C-level performance
- `tokio` async/await → native support for the concurrent agent message passing model
- `tonic` (gRPC) + `serde` → mature, production-proven ecosystem for Bus 1 (Controllo)
- `openraft` → consensus for ADR-004 (Gossip+Raft hybrid)

**Why Swift + Metal for Magellano:**
- Swift is the only path to custom Metal GPU kernels on Apple Silicon
- Measured 8.81× speedup vs CPU inference (Metal vs CPU benchmark on M2)
- ANE (Apple Neural Engine) access requires Swift/Obj-C bridging — not available from Rust directly
- CoreML model optimization pipeline is Swift-native
- NF4 quantization (6.6GB → 1.7GB) leverages Apple-specific compression paths

**Why C FFI as the bridge:**
- C is the universal ABI — both Rust (`extern "C"`) and Swift (`@_silgen_name` / `@convention(c)`) support it natively
- Marshalling overhead is negligible for batch calls (inference requests are not high-frequency control messages)
- Clean separation: Rust never touches Metal, Swift never touches gRPC

**Why not Option A (Rust only):**
- No access to custom Metal kernels → Magellano would require full reimplementation (~12 months)
- Would lose Apple-specific optimizations that produce the 8.81× speedup
- `metal-rs` crate exists but provides only low-level bindings, not the ANE/CoreML pipeline

**Why not Option C (custom language):**
- 3+ years to build a compiler
- Zero ecosystem — no gRPC, no consensus libraries, no ML tooling
- Team acquisition becomes impossible

---

## Consequences

**Positive:**
- Kernel achieves C-level latency with memory safety
- Magellano achieves native Apple Silicon performance
- Clear separation of concerns: orchestration vs inference

**Negative / Mitigations:**
- **Build complexity:** `cargo` + `swift build` + C bridge → requires unified build system (`Makefile` or `just`) → *mitigated by Makefile at repo root*
- **Cross-language debugging:** stack traces not unified → requires explicit instrumentation at the FFI boundary → *mitigated by OTel spans crossing the bridge*
- **Portability:** Swift limits local inference to Apple platforms → *mitigated by InferenceBackend HAL (see ADR-003)*
- **Team skills:** requires proficiency in both Rust AND Swift → *acknowledged, addressed in CONTRIBUTING.md*

---

## Alternatives Rejected

| Alternative | Reason rejected |
|-------------|----------------|
| Rust only | No custom Metal kernels; full Magellano reimplementation needed |
| Swift only | Unsuitable for OS-level kernel; immature systems ecosystem |
| Python for kernel | GIL prevents true parallelism; latency unacceptable for real-time orchestration |
| Go for kernel | GC pauses; gRPC performance lower than tonic |
| Custom language | 3+ years compiler dev; zero ecosystem |

---

## Related

- ADR-003: Magellano Default Engine vs Model-Agnostic (defines the Rust↔Swift contract via HAL trait)
- GAP-13: InferenceBackend Rust trait (7 methods) — the concrete interface at the C FFI boundary
- TDD v5.1, Parte B: Magellano Inference Engine specification
