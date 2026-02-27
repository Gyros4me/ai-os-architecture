# ADR-006: 3-Bus Communication Architecture

**Status:** Accepted  
**Date:** 2026-02-17  
**Authors:** Alessandro La Gamba  
**Deciders:** Architecture team  

---

## Context

A multi-agent OS with 5 macro-agents, 50+ meso-agents, and 4M micro-agents requires a communication substrate that satisfies conflicting requirements simultaneously:

1. **Control plane:** Low latency (<10ms), strong ordering, request/response semantics, typed schemas
2. **Data plane:** High throughput (logs, metrics, feedback events), pub/sub fan-out, durable delivery
3. **Tensor plane:** Ultra-low latency (<1µs), zero-copy, no serialization overhead for GPU tensors
4. **Federation plane:** Encrypted, authenticated inter-OS communication across WireGuard mesh

A single message bus cannot satisfy all four requirements. Kafka is high throughput but 10–50ms latency. gRPC is low latency but not suited for pub/sub fan-out. Shared memory is sub-microsecond but requires same-process participants.

Three approaches were evaluated:
- **Option A:** Single bus (Kafka or NATS) for everything
- **Option B:** Dual bus (gRPC + NATS)
- **Option C:** Three specialized buses with a fourth for inter-OS federation

---

## Decision

**Three internal buses with distinct transports, plus Bus 4 for inter-OS constellation communication.**

```
┌──────────────────────────────────────────────────────────────────────┐
│                     0xMeridian COMMUNICATION BUSES                   │
│                                                                      │
│  BUS 1 — CONTROL (gRPC/Protobuf)                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  Kernel → Agents · Task dispatch · DAG state · Commands      │   │
│  │  Latency: 1–10ms | TLS 1.3 mTLS | Typed Protobuf schemas    │   │
│  │  Max payload: 1MB | Pattern: request/response + streaming    │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  BUS 2 — DATA (NATS JetStream)                                       │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  Agents → Kernel · Feedback events · Logs · Metrics · Billing│   │
│  │  Latency: 10–100ms | JSON-RPC 2.0 | Durable pub/sub         │   │
│  │  Max payload: 10MB | Pattern: pub/sub, fan-out, stream replay │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  BUS 3 — TENSORS (Shared Memory / Zero-Copy)                         │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  Magellano ↔ Memory Agent · Embedding tensors · KV cache     │   │
│  │  Latency: <1µs | Binary header 48B + raw tensor data        │   │
│  │  Max payload: unlimited | Pattern: produce/consume handle    │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  BUS 4 — INTER-OS (gRPC mTLS + WireGuard Mesh)                       │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  Ambassador → Constellation · ZK-SLA · Federated metrics     │   │
│  │  Latency: <50ms | WireGuard E2E | Proof payloads + metadata  │   │
│  │  Max payload: 10MB | Pattern: request/proof, gossip          │   │
│  └──────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘
```

### Bus 1 — Control: Protobuf Service Definitions (excerpt)

```protobuf
syntax = "proto3";
package aios.control.v1;

// Kernel → Planner: dispatch a new task
service TaskDispatch {
  rpc SubmitTask (TaskRequest) returns (TaskAck);
  rpc StreamDAGUpdates (DAGSubscription) returns (stream DAGEvent);
  rpc CancelTask (CancelRequest) returns (CancelAck);
}

message TaskRequest {
  string task_id    = 1;
  string task_type  = 2;
  bytes  payload    = 3;         // serialized task parameters
  int32  priority   = 4;         // 0-100, higher = more urgent
  int64  deadline_ms = 5;        // absolute unix ms
}
```

### Bus 2 — Data: NATS Subject Hierarchy

```
aios.feedback.{agent_id}.{session_id}   → FeedbackRecord (QLoRA input)
aios.metrics.{agent_id}.{metric_name}   → MetricPoint (Prometheus bridge)
aios.events.{agent_id}.{event_type}     → AgentEvent (audit log)
aios.billing.{tenant_id}.{interval}     → BillingRecord (usage metering)
aios.logs.{agent_id}.{level}            → LogRecord (structured logging)
```

### Bus 3 — Tensors: Binary Frame Format

```
TensorHandle (48-byte header):
┌────────────┬──────────┬──────────┬──────────┬──────────────────────────┐
│ magic (4B) │ shape[0] │ shape[1] │ dtype(4B)│ shm_offset (8B) + len(8B)│
│  0xA105    │  uint32  │  uint32  │ f32/bf16 │  absolute offset in SHM  │
└────────────┴──────────┴──────────┴──────────┴──────────────────────────┘
```

The consumer receives the 48-byte handle over Bus 1 (gRPC), then reads the tensor directly from shared memory — zero copy, zero serialization.

---

## Rationale

### Why not a single bus

| Requirement | gRPC | NATS | Shared Mem |
|-------------|------|------|------------|
| Control (<10ms, typed) | ✅ | ⚠️ (higher) | ❌ (no remote) |
| High-throughput pub/sub | ❌ (not native) | ✅ | ❌ |
| Zero-copy tensors | ❌ | ❌ | ✅ |
| Durable replay | ❌ | ✅ (JetStream) | ❌ |

No single technology covers all four rows. The three-bus approach assigns each transport to its optimal use case, with zero overlap.

### Why gRPC for Bus 1

- **Typed schemas** via Protobuf prevent payload format drift across 50+ agents
- **mTLS** authentication is built in — no separate auth layer
- **Bidirectional streaming** supports DAG event subscription without polling
- **Reflection** allows runtime schema inspection for debugging

### Why NATS JetStream for Bus 2

- **Fan-out pub/sub** natively: one FeedbackRecord published → QLoRA trainer, Observability, Audit Log all receive without point-to-point wiring
- **JetStream persistence** provides at-least-once delivery for billing records — no event loss on crash
- **Subject-based routing** maps cleanly to agent/tenant/metric hierarchy
- **Embedded server** option: NATS can run as a library inside the Rust kernel, no separate process

### Why Shared Memory for Bus 3

Tensor embeddings from Magellano are 4096 floats (16KB). Serializing this over gRPC for every RAG lookup would add 100–200µs per call and spike CPU load. Shared memory reduces this to <1µs with zero CPU overhead. On Apple Silicon, Unified Memory means the same physical pages are accessible from both CPU (OCaml agent) and GPU (Magellano Metal shader) without any copy.

### Why a separate Bus 4 for federation

Inter-OS communication crosses trust boundaries: data leaving the local process must be encrypted, authenticated, and proven. Mixing inter-OS and intra-OS traffic on the same bus would either compromise local performance (encryption overhead) or security (unencrypted local traffic leaks on the same channel).

---

## Consequences

**Positive:**
- Each bus is tuned for its workload → optimal latency/throughput tradeoffs
- Bus 3 zero-copy: RAG embedding lookup reduces from ~200µs (gRPC serialize) to <1µs
- NATS JetStream ensures no feedback events lost during QLoRA training window
- Clear separation of concerns → each bus can be upgraded independently

**Negative / Mitigations:**
- **Operational complexity:** 3 transport stacks to monitor → *mitigated by unified Prometheus metrics endpoint for all buses (`aios_bus_*` metrics)*
- **Bus 3 is process-local:** Tensors cannot cross machine boundaries → *by design; cross-machine tensor transfer uses Bus 4 with explicit serialization and encryption*
- **NATS embedding in Rust kernel increases binary size by ~8MB** → *acceptable; NATS server is <10MB and eliminates external dependency*

---

## Alternatives Rejected

| Alternative | Reason rejected |
|-------------|----------------|
| Single Kafka bus | 10–50ms latency unacceptable for control plane; no shared memory option |
| gRPC only | No native pub/sub; tensor serialization overhead; no replay/durability |
| ZeroMQ | Lacks JetStream-style persistence; no authentication built in |
| Unix domain sockets only | No inter-process fan-out; no typed schema enforcement |
| Apache Pulsar | Heavier than NATS; JVM dependency conflicts with Rust/OCaml kernel |

---

## Related

- ADR-001: Rust + Swift Polyglot — defines which language owns each bus endpoint
- ADR-004: Gossip + Raft — Gossip runs alongside Bus 2 (NATS) but is a separate overlay, not a NATS topic
- ADR-012: WireGuard Mesh — the physical transport layer for Bus 4
- ADR-030: Federated Constellation — Bus 4 protocol details
- TDD v5.1, Parte B.1–B.3: Full Protobuf service definitions for all 5 Bus 1 services
