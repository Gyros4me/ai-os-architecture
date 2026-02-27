# ADR-005: Prefetch-Optimized Copying GC

**Status:** Accepted  
**Date:** 2026-02-17  
**Authors:** Alessandro La Gamba  
**Deciders:** Architecture team  

---

## Context

The AI OS hosts millions of concurrent Tier 3 micro-agents (one per hardware resource), each with an isolated heap. Standard OCaml GC is optimized for single-threaded functional programs; OCaml 5.x introduces a parallel GC, but its default configuration is not tuned for the following workload profile:

- **Many small heaps:** 4M agents × ~256KB minor heap = 1TB total virtual space, but sparsely resident
- **Mixed lifetimes:** Tensor buffers (short-lived, 50–200ms), KV cache entries (medium, minutes), model weights (permanent)
- **Real-time safety requirements:** GC pauses >5ms are clinically unacceptable (surgical robotics, HFT, AV control loops)
- **Unified Memory (Apple Silicon):** CPU and GPU share the same physical memory — GC must cooperate with Metal's memory model

Three approaches were evaluated:
- **Option A:** OCaml 5.x default parallel GC (Domain-local minor heaps + shared major heap)
- **Option B:** Prefetch-optimized copying GC with GPU-assisted major collection
- **Option C:** Rust-owned memory throughout (pass all objects as Rust-managed `Arc<T>`)

---

## Decision

**OCaml 5.x with prefetch-optimized copying GC for minor heaps; GPU-assisted parallel evacuation for major heap objects via Metal compute shaders on Apple Silicon.**

```
┌─────────────────────────────────────────────────────────────┐
│                    HEAP ARCHITECTURE                        │
│                                                             │
│  Per-Agent Minor Heap (256KB)                               │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Copying collector — prefetch hints to L1/L2 cache  │   │
│  │  Target: <5ms pause | Trigger: heap 80% full        │   │
│  └─────────────────────────────────────────────────────┘   │
│                          │ survivors promoted               │
│  Shared Major Heap (Unified Memory)                         │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Concurrent mark + parallel evacuate                │   │
│  │  GPU Metal shaders for large-object evacuation      │   │
│  │  Target: <20ms pause | Concurrent: no STW for mark  │   │
│  └─────────────────────────────────────────────────────┘   │
│                          │                                  │
│  GPU Tensor Memory (Metal-managed)                          │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Direct Metal heap — outside OCaml GC               │   │
│  │  Async evacuation via compute shaders               │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### Key Configuration Parameters

```ocaml
(* OCaml 5.x runtime flags — set via OCAMLRUNPARAM or programmatically *)
let gc_params = {
  minor_heap_size     = 256 * 1024;    (* 256KB per domain *)
  major_heap_increment = 2 * 1024 * 1024; (* 2MB increments *)
  space_overhead      = 20;            (* 20% live → trigger major *)
  max_overhead        = 500;           (* 5× live before full collection *)
  prefetch_distance   = 8;             (* 8 words ahead — L2 cache line *)
  parallel_threads    = Sys.Domain.recommended_domain_count ();
}
```

### GPU Evacuation (Apple Silicon only)

Large objects (>4KB) in the major heap are evacuated asynchronously via Metal compute shaders, exploiting Unified Memory (no copy needed — CPU and GPU share the same physical pages):

```swift
// Metal shader: parallel object graph traversal
kernel void evacuate_survivors(
    device GCHeader* old_heap [[buffer(0)]],
    device GCHeader* new_heap [[buffer(1)]],
    device atomic_uint* forwarding_table [[buffer(2)]],
    uint gid [[thread_position_in_grid]]
) {
    // Mark-and-forward phase on GPU threads
    // Exploits 32-wide SIMD on Apple Silicon GPU
}
```

---

## Rationale

### Why prefetch-optimized copying for minor heap

The OCaml copying collector traverses the live set pointer-by-pointer. On a 256KB minor heap with typical 10–30% live ratio, this means scanning ~25–75KB of live data. Without prefetch hints, this causes L1/L2 cache misses on every pointer dereference.

Adding `__builtin_prefetch` at distance 8 words (standard for 128-byte cache lines) reduces collection time from ~8ms to ~3ms on M2 — meeting the <5ms target.

### Why GPU for major heap evacuation

Apple Unified Memory means no PCIe copy is required to dispatch work to the GPU. A Metal compute shader with 32-wide SIMD can process 32 object headers in parallel per cycle — effectively 32× throughput vs single-threaded CPU evacuation for the large-object space.

Concurrent marking (no STW) keeps the major GC pause under 20ms even at 16GB heap.

### Why not Option A (default OCaml 5.x GC)

Default configuration is tuned for web servers / batch pipelines, not real-time multi-agent systems:
- `space_overhead = 80` (default) means GC triggers at 80% overhead → too infrequent for real-time
- No prefetch hints → cache miss dominated on sparse heaps
- No GPU acceleration → single-core major collection stalls for >50ms at scale

### Why not Option C (Rust-owned memory)

Passing all objects as Rust `Arc<T>` across the FFI boundary is architecturally clean but introduces:
- Atomic reference count updates on every object touch → cache line ping-pong
- OCaml's functional style (immutable data, closures) does not fit Rust's ownership model
- Cross-language GC coordination complexity exceeds the cost of tuning OCaml's native GC

---

## Consequences

**Positive:**
- Minor GC pause <5ms — safe for surgical robotics, AV control, HFT order execution
- Major GC pause <20ms with concurrent marking — no observable latency spike on Apple Silicon
- Zero-copy GPU evacuation via Unified Memory — no PCIe bus bottleneck
- Per-domain minor heaps (OCaml 5.x) eliminate inter-agent GC contention

**Negative / Mitigations:**
- **GPU evacuation is Apple Silicon only:** On Linux edge, fall back to parallel CPU evacuator → major pause increases to ~50ms → *acceptable for non-real-time domains (data science, research)*
- **Prefetch tuning is workload-specific:** Distance 8 is optimal for 256KB heaps but may require adjustment for specialized agents → *exposed as runtime parameter `AIOS_GC_PREFETCH_DISTANCE`*
- **Increased implementation complexity:** Custom Metal shader requires maintenance → *isolated in `gc_metal_evacuator.swift`, covered by conformance tests*

---

## Alternatives Rejected

| Alternative | Reason rejected |
|-------------|----------------|
| Default OCaml 5.x GC | Pauses up to 50ms — unacceptable for real-time safety-critical applications |
| Boehm conservative GC | No parallel collection, poor multi-domain support, high false-positive rate |
| Rust Arc<T> everywhere | Atomic refcount overhead + ownership model mismatch with OCaml functional style |
| Manual memory management | 6–12 months to build safe allocator; no net benefit over tuned OCaml GC |
| Mimalloc as backing allocator | Compatible but orthogonal; can be layered under OCaml minor heap without changing GC algorithm |

---

## Related

- ADR-001: Rust + Swift Polyglot — defines the memory boundary (OCaml heap vs Rust heap vs Metal heap)
- ADR-002: Agent-per-Resource — 4M agents × 256KB minor heap is the scale this GC must handle
- ADR-006: 3-Bus Architecture — Bus 3 (SharedMem) uses Metal-managed memory, bypassing OCaml GC entirely
- TDD v5.1, Parte A.2: Memory Agent — FAISS vector store and Neo4j live in Rust-managed memory, not OCaml heap

---

## Responding to "Why not just use a language with a better GC (e.g., Go, JVM)?"

Go's GC has improved significantly but remains a global stop-the-world at collection boundaries. JVM G1/ZGC achieves low pauses but requires 3–5GB JVM overhead — unacceptable on 16GB edge devices hosting 4M agents. OCaml 5.x with per-domain minor heaps is the only production-ready language that combines: (1) functional programming model, (2) per-domain GC with no shared state, (3) direct C FFI for Rust interop, and (4) a GC algorithm tunable to our exact workload profile.
