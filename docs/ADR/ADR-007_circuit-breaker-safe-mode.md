# ADR-007: Circuit Breaker per Service with Safe Mode

**Status:** Accepted  
**Date:** 2026-02-17  
**Authors:** Alessandro La Gamba  
**Deciders:** Architecture team  

---

## Context

The AI OS runs multiple interdependent components that can fail independently: the Haskell Planner (laziness + GC), the Magellano inference engine (OOM, Metal errors), external Cloud APIs (network partitions, rate limits), and the OCaml executor (logic errors, timeout). Without isolation, a single component failure cascades:

- Planner crash → Executor has no DAG → entire request pipeline stalls
- Magellano OOM → all inference blocked → system becomes unresponsive
- Cloud API rate limit → retries flood the network → amplify the outage

The naive solution — catching exceptions and retrying — does not protect against sustained failures and can make degradation worse (retry storm pattern).

Three patterns were evaluated:
- **Option A:** Exponential backoff with jitter (retry only)
- **Option B:** Circuit breaker (fail fast, automatic recovery)
- **Option C:** Circuit breaker + explicit Safe Mode (pre-computed fallbacks for emergencies)

---

## Decision

**Per-service circuit breaker (Closed → Open → Half-Open) with an additional Safe Mode tier triggered when both primary and fallback services fail.**

```
                    ┌─────────────────────────────┐
                    │      CIRCUIT BREAKER FSM     │
                    └─────────────────────────────┘

  ┌──────────┐  error_count ≥ 5      ┌──────────┐
  │  CLOSED  │ ─────────────────────► │   OPEN   │
  │ (Normal) │                        │(Fallback)│
  └──────────┘ ◄───────────────────── └──────────┘
       ▲          success_rate > 90%       │
       │                               T_halfopen
       │         ┌─────────────┐           │
       └─────────│  HALF-OPEN  │ ◄─────────┘
    success      │  (10%→100%) │
                 └─────────────┘
                       │
                 fallback fails
                       │
                       ▼
                ┌─────────────┐
                │  SAFE MODE  │
                │ (Emergency) │
                └─────────────┘
```

### State Machine Specification

```rust
pub struct CircuitBreaker {
    service_id:      ServiceId,
    state:           BreakerState,
    error_count:     AtomicU32,
    window_start:    Instant,
    window_duration: Duration,   // default: 60s
    error_threshold: u32,        // default: 5
    halfopen_ratio:  f32,        // 0.1 → 0.5 → 1.0 ramp
    t_halfopen:      Duration,   // default: 30s
    fallback:        Box<dyn ServiceFallback>,
    safe_mode_ops:   Vec<SafeOp>, // pre-approved operation list
}

#[derive(Debug, Clone, PartialEq)]
pub enum BreakerState {
    Closed,
    Open { opened_at: Instant },
    HalfOpen { probe_ratio: f32 },
    SafeMode,
}
```

### Service-Specific Fallback Map

| Primary Service | Fallback | Safe Mode Behaviour |
|-----------------|----------|---------------------|
| Haskell Planner | OCaml greedy planner | Template-based plans (pre-computed) |
| Magellano 3.3B | llama.cpp GGUF Q4 | Magellano 77M (minimal model) |
| Cloud API | llama.cpp local | Cached responses from last 24h |
| External Tool | Mocked response | Return `ToolUnavailable` with explanation |
| NATS JetStream | SQLite WAL (local) | Drop non-critical events, buffer critical |
| Memory Agent (FAISS) | BM25 keyword search | Return top-3 from static knowledge base |

### Thresholds (configurable via `breaker_config.toml`)

```toml
[planner_breaker]
window_duration_s   = 60
error_threshold     = 5
half_open_timeout_s = 30
probe_ramp          = [0.1, 0.5, 1.0]
safe_mode_trigger   = "fallback_consecutive_failures >= 3"

[magellano_breaker]
window_duration_s   = 30    # faster reaction for inference
error_threshold     = 3
half_open_timeout_s = 15
safe_mode_trigger   = "fallback_consecutive_failures >= 2"
```

---

## Rationale

### Why circuit breaker over retry-only

Exponential backoff with jitter solves transient errors (single request timeout). It does not solve **sustained failures**:
- If the Haskell Planner process is OOM-killed, retrying on the same process achieves nothing
- During a Cloud API rate limit window (minutes), retrying consumes quota slots of other tenants
- The circuit breaker *fails fast* after threshold: caller gets immediate error (1ms) instead of timeout (30s)

### Why Safe Mode as a fourth tier

The three-state circuit breaker (Closed/Open/Half-Open) assumes the fallback is always available. In practice:
- If Magellano 3.3B is OOM, llama.cpp may also be OOM (same device)
- If NATS is down, the fallback (SQLite WAL) may have an I/O error

Safe Mode provides a **pre-computed, stateless fallback** that has no runtime dependencies. Template plans are loaded at boot and held in read-only memory — they cannot fail. This guarantees liveness even under catastrophic multi-component failure.

### Why per-service (not global) circuit breakers

A global circuit breaker would block all requests if any single component fails. The Haskell Planner failing should not prevent the Interface Agent from returning cached responses. Per-service isolation ensures maximum availability of non-failing components.

---

## Consequences

**Positive:**
- Fast failure propagation: <1ms to detect broken circuit vs 30s timeout per request
- Automatic recovery: Half-Open probing eliminates need for manual intervention
- Safe Mode guarantees minimum viable functionality during catastrophic failures
- Observability: every state transition emits a `breaker_state_change` event to NATS → Prometheus alert

**Negative / Mitigations:**
- **Template plans in Safe Mode are outdated:** Pre-computed plans do not reflect current context → *acceptable; Safe Mode is emergency-only, not steady-state*
- **Half-Open probe ratio requires tuning:** Aggressive ramp (10%→100% in one step) can re-trigger the breaker → *ramp is configurable per service; default [0.1, 0.5, 1.0] is conservative*
- **Multiple independent breakers increase state surface:** Debugging requires checking all breakers, not just one → *mitigated by central `GET /health/breakers` endpoint exposing all states*

---

## Alternatives Rejected

| Alternative | Reason rejected |
|-------------|----------------|
| Retry with exponential backoff only | Does not prevent cascade during sustained failures; retry storm risk |
| Single global circuit breaker | Too coarse — one failing component blocks everything |
| Bulkhead pattern alone | Isolates thread pools but doesn't provide automatic recovery or safe mode |
| Manual failover runbooks | Requires human intervention; MTTR measured in minutes vs automatic recovery in <30s |

---

## Related

- ADR-003: Magellano HAL — the InferenceBackend fallback chain is the inference-layer circuit breaker
- ADR-026: Cryptographic Human Override — Safe Mode can be exited by human override signature
- TDD v5.1, Addendum C.2: Error Recovery scenarios — partition handling, partial DAG failure
- TDD v5.1, Parte G: Observability — `aios_circuit_breaker_state` and `aios_circuit_breaker_trips_total` metrics

## Responding to "Why not just use Kubernetes health checks and pod restarts?"

Kubernetes restarts the pod (seconds to minutes MTTR). The circuit breaker protects the *requesting* component from hanging while the pod restarts. Both are needed: Kubernetes for process recovery, circuit breaker for request isolation during the recovery window.
