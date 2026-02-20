---
title: "AI OS — Technical Design Document"
subtitle: "Complete Architecture of the AI-Native Operating System"
author: "Alessandro La Gamba"
date: "2026-02-20"
version: "5.1 — Unified Consolidation + Addendum"
lang: en
toc: true
toc-depth: 3
geometry: "margin=2.5cm"
fontsize: 11pt
documentclass: report
header-includes:
  - \usepackage{fancyhdr}
  - \pagestyle{fancy}
  - \fancyhead[L]{AI OS — Technical Design Document v5.1}
  - \fancyhead[R]{\thepage}
  - \fancyfoot[C]{Confidential — Alessandro La Gamba}
---

\newpage

# Preface

This document unifies AI OS technical specifications v1-v4 into a complete Technical Design Document. It covers the entire AI-native operating system architecture: from agent taxonomy to deployment strategy, encompassing API contracts, data model, architectural decisions, observability, security, multi-tenancy, and accessibility.

**Consolidated source documents:**

- **v1** — Agent Taxonomy (3-Tier), Inference HAL, 5 Sequence Diagrams E2E
- **v2** — API Contracts gRPC (3 Bus), Data Model (Tiered Storage), ADR-001÷004
- **v3** — Observability Platform, Security Threat Model, Deployment Strategy
- **v4** — Data Pipeline & ETL, Multi-Tenancy, Accessibility

**Resolved GAPs:** GAP-01, GAP-03, GAP-04, GAP-05, GAP-10, GAP-11, GAP-12, GAP-13 (all closed).

**Project Timeline:** 36 months (3 phases: α Foundation, β Scale, γ Enterprise)

\newpage


# Part I — Agent Architecture

## PART A: UNIFIED AGENT TAXONOMY (GAP-11)

### A.1 The Problem

The HLD diagram shows 5 agent types (Planner, Executor, Critic, Memory, Interface) operating as strategic entities with 6 sub-layers each. The Deep Analysis describes millions of micro-agents (one per page frame, one per CPU core, one per network connection) collaborating via bio-inspired algorithms.

These two visions are not in conflict — they are **complementary hierarchical levels**. The relationship between them, however, was never made explicit.

### A.2 3-Tier Model

```
┌─────────────────────────────────────────────────────────────────────┐
│  TIER 1: MACRO-AGENTS (Strategic)                                  │
│  Istances: 5-20 | Lifetime: session/permanent | Stateful           │
│  Communication: FIPA-ACL on gRPC | Decisions: LLM-powered           │
├─────────────────────────────────────────────────────────────────────┤
│  TIER 2: MESO-AGENTS (Middleware/Orchestration)                    │
│  Istances: 50-500 | Lifetime: task/session | Semi-stateful           │
│  Communication: JSON-RPC on NATS | Decisions: rule-based             │
├─────────────────────────────────────────────────────────────────────┤
│  TIER 3: MICRO-AGENTS (Operation)                                   │
│  Istances: 1K-4M+ | Lifetime: ephemeral/task | Stateless/lightweight   │
│  Communication: binary on shared memory | Decisions: bio-inspired    │
└─────────────────────────────────────────────────────────────────────┘
```

### A.3 Tier 1 — Macro-Agents (Strategic)

These are the system's "executives." Each macro-agent has a global view, accesses the LLM context, and makes strategic decisions.

| Agent | Responsibility | Sub-layer (from HLD) | Input | Output |
|-------|---------------|---------------------|-------|--------|
| **Planner** | Goal decomposition into DAG, strategy selection, time estimation | Goal Analysis, Strategy, Algorithms, Dependency, Execution, Collaboration | User intent (NL), session context, knowledge graph | Task DAG with priorities, timeline, estimated resources |
| **Executor** | Execution of atomic tasks: code gen, tool calling, API invocation | Code Gen, Tool Use, API, Sandbox, File Ops, Process Mgmt | Atomic task from DAG, context, parameters | Execution result, log, metrics |
| **Critic** | Output validation, quality scoring, security audit, fact checking | Output Validation, Code Review, Security, Fact Check, Style, Performance | Output to validate, success criteria, baseline | Quality score, structured feedback, approve/reject |
| **Memory** | RAG, embedding, indexing, knowledge graph management, caching | Embedding, Storage, Index, Vector, Retrieval, Cache | Semantic query, documents to ingest, context | Retrieval results with scores, embeddings, context window |
| **Interface** | I/O handling, protocol adaptation, formatting, session management | I/O Handler, Protocol Adapter, Data Formatter, Session, Rate Limiter, Security Filter | Raw input (HTTP, gRPC, audio, text), output to format | Normalized input, formatted output for channel |

**Properties:**
- **Singleton or limited pool** — max 3-5 instances per type (for load balancing)
- **LLM-powered** — use Magellano for reasoning (Planner, Executor, Critic)
- **Stateful** — maintain conversation context and decision history
- **Rich communication** — FIPA-ACL performatives (request, inform, propose, reject)
- **Long lifecycle** — live for the entire user session or permanently

### A.4 Tier 2 — Meso-Agents (Middleware)

These are the "middle managers." They handle orchestration, discovery, and coordination between Tier 1 and Tier 3.

| Agent | Responsibility | Typical Instances | Communication |
|-------|---------------|----------------|---------------|
| **Registry Agent** | Service discovery, agent lookup, capability matching | 3-5 (shard gossip) | Gossip protocol, heartbeat |
| **Consensus Agent** | Multi-agent mutual agreements, conflict resolution, voting | 3-7 (Raft/PBFT quorum) | Raft RPC, ballot messages |
| **Router Agent** | Message routing, load distribution, ACO pheromone | 10-50 (per zone) | Pheromone trail updates |
| **Monitor Agent** | Health check, heartbeat, failure detection, alerting | 5-20 (per service) | Heartbeat/ping, NATS events |
| **State Agent** | Checkpoint coordination, journal management, state replication | 3-10 (per tier storage) | State sync protocol |
| **Security Agent** | Policy enforcement, threat detection, ACL evaluation | 5-20 (per trusted zone) | Internal API, audit log |

**Properties:**
- **Managed pool** — auto-scale with load
- **Rule-based** — deterministic decisions, no LLM
- **Semi-stateful** — maintain operational state (routing table, registers, checkpoints)
- **Structured communication** — JSON-RPC 2.0 over NATS/WebSocket
- **Medium lifecycle** — live for the duration of a complex task or session

### A.5 Tier 3 — Micro-Agents (Operational)

These are the individual "workers." Ultra-lightweight, they operate on single resources.

| Agent | Managed Resource | Instances | RAM Overhead/Agent | Communication |
|-------|----------------|---------|------------------------|---------------|
| **Page Agent** | Physical memory frame (4KB) | ~4M per 16GB RAM | ~64 bytes (struct) | Topic: page_fault, pressure_event |
| **Core Agent** | Single CPU core | 1 per core (4-16) | ~256 bytes | Topic: load_report, dvfs_command |
| **Connection Agent** | Socket/network flow | 1 per active connection | ~128 bytes | Topic: conn_state, qos_update |
| **Device Agent** | I/O device (NVMe, NIC) | 1 per device | ~512 bytes | Topic: io_request, completion |
| **Buffer Agent** | Slot in buffer pool | 1 per allocated slot | ~32 bytes | Fence/completion handler |
| **Route Agent** | Path in routing table | 1 per active route | ~96 bytes | Pheromone update |

**Properties:**
- **Massive population** — millions of simultaneous instances
- **Stateless or minimal-state** — only the managed resource state (busy/free, temperature, latency)
- **Bio-inspired** — ant colony (scheduling), pheromones (routing), consensus (OOM)
- **Minimal communication** — binary messages on shared memory, topic-based pub/sub
- **Ephemeral lifecycle** — created/destroyed with the resource (page allocated/deallocated, connection opened/closed)

### A.6 Cross-Tier Interactions

```
              TIER 1 (Macro)                    TIER 2 (Meso)                   TIER 3 (Micro)
              ┌──────────┐                      ┌──────────┐                    ┌──────────┐
              │ Planner  │ ──── FIPA request ──▶│ Registry │ ──── lookup ──────▶│ Core[0]  │
              │          │                      │  Agent   │                    │ Core[1]  │
              │          │◀── FIPA inform ──────│          │◀── load_report ───│ Core[N]  │
              └──────────┘                      └──────────┘                    └──────────┘
                   │                                 │
                   │ task_dispatch                    │ checkpoint_trigger
                   ▼                                 ▼
              ┌──────────┐                      ┌──────────┐                    ┌──────────┐
              │ Executor │ ──── execute ───────▶│  State   │ ──── fence ───────▶│ Buffer[0]│
              │          │                      │  Agent   │                    │ Buffer[1]│
              │          │◀── completion ───────│          │◀── done ──────────│ Buffer[N]│
              └──────────┘                      └──────────┘                    └──────────┘
                   │
                   │ output_to_validate
                   ▼
              ┌──────────┐                      ┌──────────┐                    ┌──────────┐
              │  Critic  │ ──── scan_request ──▶│ Security │ ──── acl_check ──▶│ Conn[0]  │
              │          │                      │  Agent   │                    │ Conn[1]  │
              │          │◀── scan_result ──────│          │◀── acl_result ────│ Conn[N]  │
              └──────────┘                      └──────────┘                    └──────────┘
```

**Communication Rules:**
1. **Tier 1 → Tier 3: NEVER direct.** Macro-agents emit high-level intents that meso-agents translate into commands for micro-agents.
2. **Tier 3 → Tier 1: only via aggregation.** Micro-agents emit events on the bus. Meso-agents aggregate them and present them to macro-agents as metrics or alerts.
3. **Tier 2 ↔ Tier 2: peer coordination.** Registry, Consensus, and Router communicate with each other to maintain middleware coherence.
4. **Tier 3 ↔ Tier 3: bio-inspired.** Micro-agents communicate peer-to-peer (e.g., page agents in the same NUMA zone) with minimal messages on shared memory.

### A.7 Agent Identity Schema

Every agent in the system has a structured identifier:

```
{tier}.{type}.{instance_id}@{zone}

Examples:
  macro.planner.001@global          — Planner main Agent 
  meso.registry.003@zone-eu         — Registry Agent shard 3, EU zone
  micro.page.0x7F3A2B00@numa-0      — Page Agent per physical frame 
  micro.core.2@cpu-cluster-0        — Core Agent per core #2
```

### A.8 Scalability: reference numbers

| Scenario | Tier 1 | Tier 2 | Tier 3 | Estimated Msg/sec |
|----------|--------|--------|--------|---------------------|
| **Dev laptop** (16GB, 4 core) | 5 | 30 | ~4M (page) + 4 (core) + ~100 (conn) | ~10K |
| **Workstation** (64GB, 16 core) | 15 | 150 | ~16M + 16 + ~1K | ~100K |
| **Server** (256GB, 64 core) | 20+ pool | 500 | ~64M + 64 + ~10K | ~1M |

---

## PART B: INFERENCE HAL SPECIFICATION (GAP-13)

### B.1 The Problem

Magellano is optimized for Apple Silicon (Swift + Metal). The kernel is written in Rust (platform-agnostic). Without an abstraction layer, the AI OS would be Apple-only. The Inference HAL solves this by binding inference backends to a unified Rust interface.

### B.2 Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                    AI OS KERNEL (Rust)                            │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │               INFERENCE HAL (Rust trait)                  │    │
│  │                                                          │    │
│  │  fn load_model(config) → Result<ModelHandle>             │    │
│  │  fn infer(handle, input) → Result<InferenceOutput>       │    │
│  │  fn embed(handle, text) → Result<Vec<f32>>               │    │
│  │  fn stream(handle, input) → Result<TokenStream>          │    │
│  │  fn unload(handle) → Result<()>                          │    │
│  │  fn capabilities() → BackendCapabilities                 │    │
│  │  fn health() → BackendHealth                             │    │
│  │                                                          │    │
│  └───────┬──────────────┬──────────────┬────────────────────┘    │
│          │              │              │                          │
│  ┌───────▼──────┐ ┌────▼───────┐ ┌────▼───────┐ ┌────────────┐  │
│  │ MagellanoBack│ │ LlamaCppBk │ │  vLLMBack  │ │ RemoteBack │  │
│  │ (Swift+Metal)│ │ (C++ CPU/  │ │ (Python    │ │ (gRPC to   │  │
│  │              │ │  CUDA)     │ │  GPU)      │ │  cloud)    │  │
│  │ Apple Silicon│ │ x86/ARM/   │ │ NVIDIA     │ │ Anthropic/ │  │
│  │ M1-M4       │ │ NVIDIA     │ │ A100/H100  │ │ OpenAI/etc │  │
│  └──────────────┘ └────────────┘ └────────────┘ └────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

### B.3 Rust Trait Definition

```rust
// inference_hal/src/lib.rs

/// Capabilities advertised by a backend
pub struct BackendCapabilities {
    pub name: String,                    // "magellano", "llama-cpp", "vllm"
    pub max_context_length: usize,       // 512, 4096, 128K, etc.
    pub supports_streaming: bool,
    pub supports_embedding: bool,
    pub supports_fine_tuning: bool,
    pub supported_quantizations: Vec<Quantization>,  // FP16, INT8, NF4
    pub max_batch_size: usize,
    pub estimated_tokens_per_sec: f64,
    pub memory_required_mb: usize,
    pub platform: Platform,              // AppleSilicon, CUDA, CPU, Cloud
}

pub enum Platform {
    AppleSilicon,  // Metal backend (Magellano)
    CUDA,          // NVIDIA GPU (vLLM, llama.cpp)
    ROCm,          // AMD GPU
    CPU,           // Universal Fallback  (llama.cpp GGUF)
    Cloud,         // remote API  (Anthropic, OpenAI)
}

pub enum Quantization {
    FP32, FP16, BF16, INT8, INT4, NF4, GGUF(String),
}

/// Model handle returned by load_model
pub struct ModelHandle {
    pub id: Uuid,
    pub backend: String,
    pub config: ModelConfig,
    pub loaded_at: SystemTime,
    pub memory_used_mb: usize,
}

/// Configuration for model loading
pub struct ModelConfig {
    pub model_path: PathBuf,           // local path or URL
    pub model_size: ModelSize,          // Tiny(77M), Small(400M), Medium(800M), Large(3.3B)
    pub quantization: Quantization,
    pub max_context: usize,
    pub device: Option<Platform>,       // None = auto-detect
}

pub enum ModelSize {
    Tiny,     // 77M  — fast intent parsing , power-save mode
    Small,    // 400M — simple tasks semlici
    Medium,   // 800M — general purpose
    Large,    // 3.3B — complex reasoning  (Magellano full)
    Custom(usize),
}

/// Core trait — every backend implements the following
#[async_trait]
pub trait InferenceBackend: Send + Sync {
    /// loads a model and gives back an handle
    async fn load_model(&self, config: ModelConfig) -> Result<ModelHandle>;
    
    /// Complete Inference  (not streaming)
    async fn infer(&self, handle: &ModelHandle, input: InferenceInput) -> Result<InferenceOutput>;
    
    /// Streaming token-by-token
    async fn stream(&self, handle: &ModelHandle, input: InferenceInput) 
        -> Result<Pin<Box<dyn Stream<Item = Result<Token>> + Send>>>;
    
    /// Generates embedding vector
    async fn embed(&self, handle: &ModelHandle, text: &str) -> Result<Vec<f32>>;
    
    /// Pulls out model from  memory
    async fn unload(&self, handle: &ModelHandle) -> Result<()>;
    
    /// Capabilities of backend
    fn capabilities(&self) -> BackendCapabilities;
    
    /// Health check
    async fn health(&self) -> BackendHealth;
}
```

### B.4 Model Router (Smart Dispatch)

Il Model Router decides which backend to use based on:

```rust
// inference_hal/src/router.rs

pub struct ModelRouter {
    backends: Vec<Box<dyn InferenceBackend>>,
    policy: RoutingPolicy,
    metrics: Arc<RouterMetrics>,
}

pub enum RoutingPolicy {
    /// Always use the fastest available local backend
    LocalFirst,
    /// Choose based on task size
    TaskAdaptive {
        simple_threshold: usize,    // <100 token → Magellano Tiny
        medium_threshold: usize,    // <1000 token → Magellano Large
        // >1000 token → cloud fallback
    },
    /// Choose based on battery/power state
    PowerAware {
        battery_low: ModelSize,     // <20% → Tiny
        battery_medium: ModelSize,  // 20-80% → Medium
        battery_high: ModelSize,    // >80% → Large
    },
    /// Round-robin tra backend per load balancing
    LoadBalanced,
    /// Fallback chain: try the first; if it fails, try the second
    FallbackChain(Vec<String>),  // ["magellano", "llama-cpp", "cloud"]
}

impl ModelRouter {
    pub async fn route(&self, request: InferenceRequest) -> Result<InferenceOutput> {
        let backend = self.select_backend(&request)?;
        
        let result = backend.infer(&request.handle, request.input).await;
        
        match result {
            Ok(output) => {
                self.metrics.record_success(backend.capabilities().name.clone());
                Ok(output)
            }
            Err(e) => {
                self.metrics.record_failure(backend.capabilities().name.clone());
                // Fall back to the next backend in the chain
                self.try_fallback(&request, e).await
            }
        }
    }
}
```

### B.5 Backend: Magellano (Swift via C FFI)

```rust
// inference_hal/src/backends/magellano.rs

/// Binding Rust → Swift via C bridge
extern "C" {
    fn magellano_init(config_path: *const c_char) -> *mut c_void;
    fn magellano_infer(
        ctx: *mut c_void,
        prompt: *const c_char,
        max_tokens: u32,
        output: *mut c_char,
        output_len: *mut u32,
    ) -> i32;
    fn magellano_embed(
        ctx: *mut c_void,
        text: *const c_char,
        output: *mut f32,
        dims: *mut u32,
    ) -> i32;
    fn magellano_free(ctx: *mut c_void);
}

pub struct MagellanoBackend {
    ctx: *mut c_void,
    config: MagellanoConfig,
}

// Safety: Metal context is thread-safe after init
unsafe impl Send for MagellanoBackend {}
unsafe impl Sync for MagellanoBackend {}

#[async_trait]
impl InferenceBackend for MagellanoBackend {
    fn capabilities(&self) -> BackendCapabilities {
        BackendCapabilities {
            name: "magellano".into(),
            max_context_length: 512,       // training limit
            supports_streaming: true,
            supports_embedding: true,
            supports_fine_tuning: true,     // QLoRA on-device
            supported_quantizations: vec![Quantization::FP16, Quantization::NF4],
            max_batch_size: 1,              // single-device
            estimated_tokens_per_sec: 2400.0,
            memory_required_mb: 10600,      // 10.6 GB
            platform: Platform::AppleSilicon,
        }
    }
    // ... method implementations
}
```

### B.6 Backend Selection Matrix

| Scenario | Primary backend | Fallback | Rationale |
|----------|-----------------|----------|-----------|
| **Apple Silicon, local task** | Magellano (Metal FP16) | llama.cpp CPU | Privacy, low latency |
| **NVIDIA GPU, task complesso** | vLLM (CUDA) | llama.cpp CUDA | Throughput massimo |
| **CPU only, edge device** | llama.cpp (GGUF Q4) | Cloud API | Only local option |
| **Task >128K context** | Cloud API (Claude/GPT) | — | Context window Magellano=512 |
| **Battery <20%** | Magellano Tiny (77M) | — | Energy saving |
| **Fine-tuning required** | Magellano (QLoRA) | — | Only one with on-device training |

---

## PART C: E2E SEQUENCE DIAGRAMS (5 Flows + v5.1 Refinements)

> **v5.1 Integration Note:** Sections C.1.A, C.2.A, C.3.A add per-component timing breakdown, distributed error scenarios, and complete learning path architecture — incorporated from the external Kimi review.

---

## PART C: E2E SEQUENCE DIAGRAMS (5 Flows)

### C.1 Happy Path — Standard User Request

```
USER          INTERFACE    PLANNER     EXECUTOR    CRITIC      MEMORY     REGISTRY
 │               │            │           │          │           │           │
 │── "Analyze   ─▶│            │           │          │           │           │
 │   Q3 sales"    │            │           │          │           │           │
 │               │──normalize──▶│           │          │           │           │
 │               │            │──lookup────┼──────────┼───────────┼──────────▶│
 │               │            │            │          │           │     capabilities
 │               │            │◀──────────┼──────────┼───────────┼──────────│
 │               │            │           │          │           │           │
 │               │            │──retrieve──┼──────────┼──────────▶│           │
 │               │            │  context   │          │  query:   │           │
 │               │            │◀───────────┼──────────┼──────────│           │
 │               │            │  results   │          │           │           │
 │               │            │           │          │           │           │
 │               │            │──DAG: [T1:fetch_data, T2:analyze, T3:format]  │
 │               │            │           │          │           │           │
 │               │            │──request──▶│          │           │           │
 │               │            │  T1: fetch │          │           │           │
 │               │            │           │─execute──┼───────────┼──────────▶│
 │               │            │           │  (tool)  │           │   tool_call
 │               │            │           │◀─────────┼───────────┼──────────│
 │               │            │           │          │           │           │
 │               │            │           │──result──▶│          │           │
 │               │            │           │          │─validate──│           │
 │               │            │           │          │  score:0.92│          │
 │               │            │           │◀─approved─│          │           │
 │               │            │           │          │           │           │
 │               │            │──request──▶│          │           │           │
 │               │            │  T2,T3     │          │           │           │
 │               │            │           │──execute─▶│──validate─│           │
 │               │            │           │          │◀─approved─│           │
 │               │            │           │          │           │           │
 │               │            │           │          │           │           │
 │               │            │──store─────┼──────────┼──────────▶│           │
 │               │            │  results   │          │  embed+   │           │
 │               │            │           │          │  index    │           │
 │               │            │           │          │           │           │
 │               │◀─response──│           │          │           │           │
 │◀──formatted──│            │           │          │           │           │
 │   report     │            │           │          │           │           │
```


### C.1.1 Happy Path Breakdown (~4.8s)

```
Phase                        Component            Duration   Note
─────────────────────────────────────────────────────────────────────
Input parsing                Interface Agent       15ms      Normalize + sanitize
FIPA routing                 Bus Controllo         3ms       gRPC hop
Registry lookup              Agent Registry        5ms       Cache hit (gossip)
Context retrieval (RAG)      Memory Agent          80ms      Vector search + rerank
  └─ Embedding query         Magellano (Metal)     25ms      77M model, 1 embedding
  └─ FAISS search            Vector Store          35ms      Top-K=5, dense+sparse
  └─ Reranking               Magellano (Metal)     20ms      Score 5 candidates
                                                   ─────
                                                   80ms      subtotal RAG

Planning                     Planner Agent         180ms     
  └─ Goal analysis           Magellano 3.3B        95ms      ~50 output tokens
  └─ DAG construction        Rule engine           15ms      No LLM needed
  └─ Strategy selection      Magellano 3.3B        70ms      ~30 output tokens
                                                   ─────
                                                   180ms     subtotal planning

Task 1: fetch_data           Executor Agent        350ms     
  └─ Code generation         Magellano 3.3B        120ms     SQL query, ~80 tokens
  └─ Sandbox execution       Docker/Wasm           200ms     Execute SQL + fetch
  └─ Critic validation       Critic Agent          30ms      Schema check
                                                   ─────
                                                   350ms

Task 2: analyze_trends       Executor Agent        1200ms    ← Critical path
  └─ Code generation         Magellano 3.3B        300ms     Python analysis, ~250 tokens  
  └─ Sandbox execution       Docker                800ms     Pandas + computation
  └─ Critic validation       Critic Agent          100ms     Fact check + quality
                                                   ─────
                                                   1200ms

Task 3: generate_viz         Executor Agent        800ms     
  └─ Code generation         Magellano 3.3B        250ms     Matplotlib, ~200 tokens
  └─ Sandbox execution       Docker                500ms     Render chart
  └─ Critic validation       Critic Agent          50ms      Format check
                                                   ─────
                                                   800ms

Synthesis                    Planner Agent         200ms     Combina risultati
Response formatting          Interface Agent       30ms      Markdown + chart embed
Memory store                 Memory Agent          45ms      
  └─ Embed results           Magellano             25ms      
  └─ Index in Vector Store   ChromaDB/FAISS        20ms      
                                                   ─────
SEQUENTIAL TOTAL:                                ~2.9s     (T1→T2→T3 sequential)
TOTAL WITH PARALLELISM:                           ~2.1s     (T1 seq, T2∥T3 paralleli)
+ Orchestration overhead:                         ~0.3s     Bus routing, serialization
                                                   ═════
E2E ESTIMATE:                                         ~2.4-2.9s (hardware M2 Ultra)
                                                   ~4.8s     (hardware M2 base/T430s)
```

**Note:** The original ~4.8s assume consumer hardware (e.g., M2 base). On M2 Ultra with 192GB unified memory, parallelism and GPU bandwidth reduce this to ~2.4s. Inference times (50-100ms per call) are correct — most of the time is in sandbox execution and orchestration.


## ADDENDUM C.2: Refined Error Path  — Distributed Scenarios Included

### C.1.A [v5.1 Refinement] — Detailed Timing Breakdown

The external review correctly notes that E2E times (~4.8-5s) merit a per-component breakdown. Magellano inference on Metal is ~50-100ms, but the total includes orchestration, I/O, RAG retrieval, and validation.

### C.1.1 Happy Path Breakdown (~4.8s)

```
Phase                        Component            Duration   Note
─────────────────────────────────────────────────────────────────────
Input parsing                Interface Agent       15ms      Normalize + sanitize
FIPA routing                 Bus Controllo         3ms       gRPC hop
Registry lookup              Agent Registry        5ms       Cache hit (gossip)
Context retrieval (RAG)      Memory Agent          80ms      Vector search + rerank
  └─ Embedding query         Magellano (Metal)     25ms      77M model, 1 embedding
  └─ FAISS search            Vector Store          35ms      Top-K=5, dense+sparse
  └─ Reranking               Magellano (Metal)     20ms      Score 5 candidates
                                                   ─────
                                                   80ms      subtotal RAG

Planning                     Planner Agent         180ms     
  └─ Goal analysis           Magellano 3.3B        95ms      ~50 output tokens
  └─ DAG construction        Rule engine           15ms      No LLM needed
  └─ Strategy selection      Magellano 3.3B        70ms      ~30 output tokens
                                                   ─────
                                                   180ms     subtotal planning

Task 1: fetch_data           Executor Agent        350ms     
  └─ Code generation         Magellano 3.3B        120ms     SQL query, ~80 tokens
  └─ Sandbox execution       Docker/Wasm           200ms     Execute SQL + fetch
  └─ Critic validation       Critic Agent          30ms      Schema check
                                                   ─────
                                                   350ms

Task 2: analyze_trends       Executor Agent        1200ms    ← Critical path
  └─ Code generation         Magellano 3.3B        300ms     Python analysis, ~250 tokens  
  └─ Sandbox execution       Docker                800ms     Pandas + computation
  └─ Critic validation       Critic Agent          100ms     Fact check + quality
                                                   ─────
                                                   1200ms

Task 3: generate_viz         Executor Agent        800ms     
  └─ Code generation         Magellano 3.3B        250ms     Matplotlib, ~200 tokens
  └─ Sandbox execution       Docker                500ms     Render chart
  └─ Critic validation       Critic Agent          50ms      Format check
                                                   ─────
                                                   800ms

Synthesis                    Planner Agent         200ms     Combina risultati
Response formatting          Interface Agent       30ms      Markdown + chart embed
Memory store                 Memory Agent          45ms      
  └─ Embed results           Magellano             25ms      
  └─ Index in Vector Store   ChromaDB/FAISS        20ms      
                                                   ─────
SEQUENTIAL TOTAL:                                ~2.9s     (T1→T2→T3 sequential)
TOTAL WITH PARALLELISM:                           ~2.1s     (T1 seq, T2∥T3 paralleli)
+ Orchestration overhead:                         ~0.3s     Bus routing, serialization
                                                   ═════
E2E ESTIMATE:                                         ~2.4-2.9s (hardware M2 Ultra)
                                                   ~4.8s     (hardware M2 base/T430s)
```

**Note:** The original ~4.8s assume consumer hardware (e.g., M2 base). On M2 Ultra with 192GB unified memory, parallelism and GPU bandwidth reduce this to ~2.4s. Inference times (50-100ms per call) are correct — most of the time is in sandbox execution and orchestration.

---

---


### C.2.1 Complete Sequence Diagram

```
USER          INTERFACE    PLANNER     EXECUTOR    CRITIC      RETRY       STATE_AGENT
 │               │            │           │          │        ORCHESTR.       │
 │── "Generate API▶│            │           │          │           │            │
 │   payments "  │            │           │          │           │            │
 │               │──forward──▶│           │          │           │            │
 │               │            │──plan DAG──│          │           │            │
 │               │            │──request──▶│          │           │            │
 │               │            │  T1: codegen│         │           │            │
 │               │            │           │─execute──│           │            │
 │               │            │           │          │           │            │
 │               │            │           │ ✖ Attempt 1: syntax error         │
 │               │            │           │──result──▶│          │            │
 │               │            │           │          │─validate──│            │
 │               │            │           │          │ FAIL:syntax│           │
 │               │            │           │◀─FAILURE─│          │            │
 │               │            │           │          │           │            │
 │               │            │           │──escalate─┼──────────▶│           │
 │               │            │           │          │  retry_1   │           │
 │               │            │           │          │           │──journal──▶│
 │               │            │           │          │           │ log_retry  │
 │               │            │           │          │           │            │
 │               │            │           │ ✖ Attempt 2: timeout (>30s)       │
 │               │            │           │──escalate─┼──────────▶│           │
 │               │            │           │          │  retry_2   │           │
 │               │            │           │          │           │──journal──▶│
 │               │            │           │          │           │            │
 │               │            │           │ ✖ Attempt 3: security violation   │
 │               │            │           │──escalate─┼──────────▶│           │
 │               │            │           │          │  MAX_RETRY │           │
 │               │            │           │          │           │──journal──▶│
 │               │            │           │          │           │ ESCALATE   │
 │               │            │◀──CANCEL──│          │           │            │
 │               │            │  T1 failed│          │           │            │
 │               │            │           │          │           │            │
 │               │            │──REPLAN───│          │           │            │
 │               │            │  Decompose into simpler sub-tasks:            │
 │               │            │  • T1a: schema database (no sandbox)          │
 │               │            │  • T1b: endpoint stub (template-based)        │
│               │            │  • T1c: API documentation                    │
 │               │            │           │          │           │            │
 │               │            │──request──▶│ T1a      │           │            │
 │               │            │           │─execute──▶│─validate──│            │
 │               │            │           │          │ OK: 0.88  │            │
 │               │            │──request──▶│ T1b      │           │            │
 │               │            │           │─execute──▶│─validate──│            │
 │               │            │           │          │ OK: 0.91  │            │
 │               │            │──request──▶│ T1c      │           │            │
 │               │            │           │─execute──▶│─validate──│            │
 │               │            │           │          │ OK: 0.85  │            │
 │               │            │           │          │           │            │
 │               │            │──synthesize: partial solution──── │            │
│               │◀──partial──│           │          │           │            │
 │◀──"Generated  │            │           │          │           │            │
│  schema & stub│            │           │          │           │            │
│  Implementat. │            │           │          │           │            │
 │  complex     │            │           │          │           │            │
 │  requires     │            │           │          │           │            │
 │  review."     │            │           │          │           │            │
```

**Duration:** ~12s (vs ~5s happy path)
**Outcome:** Partial success with transparent explanation
**User perception:** System is resilient, not broken

### C.2.2 Error Recovery Rules (Updated)

```rust
pub struct RetryPolicy {
    pub max_retries: u32,           // default: 3 (before 2)
    pub backoff: BackoffStrategy,
    pub timeout_per_attempt: Duration,
    pub escalation: EscalationPolicy,
}

pub enum BackoffStrategy {
    Exponential { base: Duration, max: Duration },  // 1s, 2s, 4s, max 30s
    Linear { step: Duration },                       // 1s, 2s, 3s
    Immediate,                                        // no delay (for syntax errors)
}

pub enum EscalationPolicy {
    ReplanAndSimplify,    // default: decompose into simpler sub-tasks
    FallbackToCache,      // use cached results if available
    DelegateToCloud,      // if error is resource-bound, try cloud backend
    PartialResponse,      // respond with what you have, explain the gaps
    HumanEscalation,      // notify admin (Enterprise only)
}
```

### C.2.3 Distributed Error Scenarios (NEW)

Additional scenarios not covered in the original version:

**Scenario A: Network Partition (Phase β multi-node)**

```
Node 1 (Kernel)    ──── PARTITION ────    Node 2 (Inference Worker)
      │                                          │
      │ Planner request → Executor                │
      │ Executor route_to("vllm") → TIMEOUT       │
      │                                          │
      │ HAL fallback chain activates:             │
      │ 1. vLLM (Node 2) → TIMEOUT (5s)          │
      │ 2. llama.cpp (local CPU) → OK (slower)    │
      │                                          │
      │ Response delivered (degraded latency)      │
      │                                          │
      │ Registry: mark Node 2 as DEGRADED         │
│ Gossip protocol: propagates in O(log N)   │
      │                                          │
      │ ──── PARTITION HEALS ────                 │
      │                                          │
      │ Node 2 heartbeat resumes                  │
      │ Registry: mark Node 2 as HEALTHY          │
      │ Routing resumes normal policy             │
```

**Scenario B: Split-Brain durante Raft Consensus**

```
Raft cluster: 3 nodes (quorum = 2)

     Node A (Leader)    Node B (Follower)    Node C (Follower)
          │                   │                    │
          │ ─── PARTITION ─── │                    │
          │                   │                    │
          │ (alone, no quorum)│──election timeout──│
          │ reads OK, writes  │                    │
          │ FAIL (no quorum)  │──vote for C────────▶│
          │                   │◀──win election─────│
          │                   │                    │ (new Leader)
          │                   │                    │
          │ ─── HEAL ─────── │                    │
          │                   │                    │
          │ discover new term │                    │
          │ step down to      │                    │
          │ Follower           │                    │
          │ sync log from C   │                    │

Impact: coordinated checkpoints fail for ~5-10s during election.
         Agent Registry reads work normally (gossip cache).
         Writes: queued, retry after election.
```

**Scenario C: Agent Crash con Checkpoint Recovery**

```
Executor Agent #3          Orchestrator          Checkpoint Manager
      │                        │                       │
      │ ✖ FATAL: MetalDeviceUnavailable               │
      │──emergency_checkpoint──▶│                       │
      │  (saving kv_cache,      │                       │
      │   partial results)      │                       │
      │ TERMINATE               │                       │
      │                        │──check crash type──────│
      │                        │                       │
      │                        │  Checkpoint exists?    │
      │                        │◀──YES, valid──────────│
      │                        │                       │
      │                        │──restart_warm──────────│
      │                        │  backoff: 1s (reduced)│
      │                        │                       │
NEW Executor Agent #3          │                       │
      │◀──restore──────────────│───────────────────────│
      │  kv_cache + context    │  checkpoint loaded     │
      │                        │                       │
      │──heartbeat─────────────▶│                       │
      │  STATUS: HEALTHY        │                       │
      │                        │──resume pending tasks──│
```

### C.2.4 Error Recovery Metrics

```
aios_retry_attempts_total{agent, task_type, attempt_number}
aios_retry_outcome{agent, outcome="success|replan|partial|escalate"}
aios_replan_count_total{agent, reason="timeout|error|quality"}
aios_recovery_duration_seconds{recovery_type="warm|cold", quantile}
aios_partition_events_total{node_pair}
aios_raft_election_duration_seconds{quantile}
aios_checkpoint_save_duration_seconds{agent, quantile}
aios_checkpoint_restore_duration_seconds{agent, quantile}
```


## ADDENDUM C.3: Complete Learning Path — Real-time Feedback + Nightly QLoRA Batch

This section fully replaces the previous C.3, integrating the end-to-end continuous learning cycle —to-end.

### C.2.A [v5.1 Refinement] — Refined Error Path — Including Distributed Scenarios

### C.2.1 Complete Sequence Diagram

```
USER          INTERFACE    PLANNER     EXECUTOR    CRITIC      RETRY       STATE_AGENT
 │               │            │           │          │        ORCHESTR.       │
 │── "Generate API▶│            │           │          │           │            │
 │   pagamenti"  │            │           │          │           │            │
 │               │──forward──▶│           │          │           │            │
 │               │            │──plan DAG──│          │           │            │
 │               │            │──request──▶│          │           │            │
 │               │            │  T1: codegen│         │           │            │
 │               │            │           │─execute──│           │            │
 │               │            │           │          │           │            │
 │               │            │           │ ✖ Attempt 1: syntax error         │
 │               │            │           │──result──▶│          │            │
 │               │            │           │          │─validate──│            │
 │               │            │           │          │ FAIL:syntax│           │
 │               │            │           │◀─FAILURE─│          │            │
 │               │            │           │          │           │            │
 │               │            │           │──escalate─┼──────────▶│           │
 │               │            │           │          │  retry_1   │           │
 │               │            │           │          │           │──journal──▶│
 │               │            │           │          │           │ log_retry  │
 │               │            │           │          │           │            │
 │               │            │           │ ✖ Attempt 2: timeout (>30s)       │
 │               │            │           │──escalate─┼──────────▶│           │
 │               │            │           │          │  retry_2   │           │
 │               │            │           │          │           │──journal──▶│
 │               │            │           │          │           │            │
 │               │            │           │ ✖ Attempt 3: security violation   │
 │               │            │           │──escalate─┼──────────▶│           │
 │               │            │           │          │  MAX_RETRY │           │
 │               │            │           │          │           │──journal──▶│
 │               │            │           │          │           │ ESCALATE   │
 │               │            │◀──CANCEL──│          │           │            │
 │               │            │  T1 failed│          │           │            │
 │               │            │           │          │           │            │
 │               │            │──REPLAN───│          │           │            │
 │               │            │  Decompose into simpler sub-tasks:            │
 │               │            │  • T1a: schema database (no sandbox)          │
 │               │            │  • T1b: endpoint stub (template-based)        │
│               │            │  • T1c: API documentation                    │
 │               │            │           │          │           │            │
 │               │            │──request──▶│ T1a      │           │            │
 │               │            │           │─execute──▶│─validate──│            │
 │               │            │           │          │ OK: 0.88  │            │
 │               │            │──request──▶│ T1b      │           │            │
 │               │            │           │─execute──▶│─validate──│            │
 │               │            │           │          │ OK: 0.91  │            │
 │               │            │──request──▶│ T1c      │           │            │
 │               │            │           │─execute──▶│─validate──│            │
 │               │            │           │          │ OK: 0.85  │            │
 │               │            │           │          │           │            │
 │               │            │──synthesize: partial solution──── │            │
│               │◀──partial──│           │          │           │            │
 │◀──"Generated  │            │           │          │           │            │
│  schema & stub│            │           │          │           │            │
│  Implementat. │            │           │          │           │            │
 │  complex     │            │           │          │           │            │
 │  requires     │            │           │          │           │            │
 │  review."     │            │           │          │           │            │
```

**Duration:** ~12s (vs ~5s happy path)
**Outcome:** Partial success with transparent explanation
**User perception:** System is resilient, not broken

### C.2.2 Error Recovery Rules (Updated)

```rust
pub struct RetryPolicy {
    pub max_retries: u32,           // default: 3 (before 2)
    pub backoff: BackoffStrategy,
    pub timeout_per_attempt: Duration,
    pub escalation: EscalationPolicy,
}

pub enum BackoffStrategy {
    Exponential { base: Duration, max: Duration },  // 1s, 2s, 4s, max 30s
    Linear { step: Duration },                       // 1s, 2s, 3s
    Immediate,                                        // no delay (for syntax errors)
}

pub enum EscalationPolicy {
    ReplanAndSimplify,    // default: decompose into simpler sub-tasks
    FallbackToCache,      // use cached results if available
    DelegateToCloud,      // if error is resource-bound, try cloud backend
    PartialResponse,      // respond with what you have, explain the gaps
    HumanEscalation,      // notify admin (Enterprise only)
}
```

### C.2.3 Distributed Error Scenarios (NEW)

Additional scenarios not covered in the original version:

**Scenario A: Network Partition (Phase β multi-node)**

```
Node 1 (Kernel)    ──── PARTITION ────    Node 2 (Inference Worker)
      │                                          │
      │ Planner request → Executor                │
      │ Executor route_to("vllm") → TIMEOUT       │
      │                                          │
      │ HAL fallback chain activates:             │
      │ 1. vLLM (Node 2) → TIMEOUT (5s)          │
      │ 2. llama.cpp (local CPU) → OK (slower)    │
      │                                          │
      │ Response delivered (degraded latency)      │
      │                                          │
      │ Registry: mark Node 2 as DEGRADED         │
│ Gossip protocol: propagates in O(log N)   │
      │                                          │
      │ ──── PARTITION HEALS ────                 │
      │                                          │
      │ Node 2 heartbeat resumes                  │
      │ Registry: mark Node 2 as HEALTHY          │
      │ Routing resumes normal policy             │
```

**Scenario B: Split-Brain durante Raft Consensus**

```
Raft cluster: 3 nodes (quorum = 2)

     Node A (Leader)    Node B (Follower)    Node C (Follower)
          │                   │                    │
          │ ─── PARTITION ─── │                    │
          │                   │                    │
          │ (alone, no quorum)│──election timeout──│
          │ reads OK, writes  │                    │
          │ FAIL (no quorum)  │──vote for C────────▶│
          │                   │◀──win election─────│
          │                   │                    │ (new Leader)
          │                   │                    │
          │ ─── HEAL ─────── │                    │
          │                   │                    │
          │ discover new term │                    │
          │ step down to      │                    │
          │ Follower           │                    │
          │ sync log from C   │                    │

Impact: coordinated checkpoints fail for ~5-10s during election.
         Agent Registry reads work normally (gossip cache).
         Writes: queued, retry after election.
```

**Scenario C: Agent Crash with Checkpoint Recovery**

```
Executor Agent #3          Orchestrator          Checkpoint Manager
      │                        │                       │
      │ ✖ FATAL: MetalDeviceUnavailable               │
      │──emergency_checkpoint──▶│                       │
      │  (saving kv_cache,      │                       │
      │   partial results)      │                       │
      │ TERMINATE               │                       │
      │                        │──check crash type──────│
      │                        │                       │
      │                        │  Checkpoint exists?    │
      │                        │◀──YES, valid──────────│
      │                        │                       │
      │                        │──restart_warm──────────│
      │                        │  backoff: 1s (ridotto) │
      │                        │                       │
NEW Executor Agent #3          │                       │
      │◀──restore──────────────│───────────────────────│
      │  kv_cache + context    │  checkpoint loaded     │
      │                        │                       │
      │──heartbeat─────────────▶│                       │
      │  STATUS: HEALTHY        │                       │
      │                        │──resume pending tasks──│
```

### C.2.4 Error Recovery Metrics

```
aios_retry_attempts_total{agent, task_type, attempt_number}
aios_retry_outcome{agent, outcome="success|replan|partial|escalate"}
aios_replan_count_total{agent, reason="timeout|error|quality"}
aios_recovery_duration_seconds{recovery_type="warm|cold", quantile}
aios_partition_events_total{node_pair}
aios_raft_election_duration_seconds{quantile}
aios_checkpoint_save_duration_seconds{agent, quantile}
aios_checkpoint_restore_duration_seconds{agent, quantile}
```

---

---


### C.3.1 Overview Architecture

AI OS implements a two-speed continuous learning system:

1. **Fast loop (real-time):** In-session feedback immediately updates the Vector Store and Knowledge Graph
2. **Slow loop (nightly batch):** Aggregated feedback generates a dataset for QLoRA fine-tuning of Magellano

```
┌──────────────────────────────────────────────────────────────────┐
│                    LEARNING ARCHITECTURE                          │
│                                                                   │
│  FAST LOOP (session)               SLOW LOOP (nightly)           │
│  ┌────────────────────┐           ┌────────────────────┐         │
│  │ User Query          │           │ Feedback Buffer    │         │
│  │      ↓              │           │ (100+ samples)     │         │
│  │ Magellano Response  │           │      ↓             │         │
│  │      ↓              │           │ Quality Filter     │         │
│  │ Critic Score        │           │ (score ≥ 0.7)      │         │
│  │      ↓              │           │      ↓             │         │
│  │ score < 0.85?       │           │ QLoRA Training     │         │
│  │  YES → Regenerate   │           │ (3 epochs, 4-bit)  │         │
│  │  NO  → Deliver      │           │      ↓             │         │
│  │      ↓              │           │ Merge Adapters     │         │
│  │ Store in Buffer     │           │      ↓             │         │
│  │ Update Vector Store │           │ Hot-Swap Deploy    │         │
│  │ Update KG           │           │      ↓             │         │
│  └────────────────────┘           │ Magellano v(N+1)   │         │
│                                    └────────────────────┘         │
└──────────────────────────────────────────────────────────────────┘
```

### C.3.2 PHASE 1: Interactive Session (Real-time Learning)

```
USER          INTERFACE    CRITIC       FEEDBACK    MAGELLANO    MEMORY
                                        BUFFER      (Runtime)
 │               │            │           │            │           │
 │ "Explain       │            │           │            │           │
 │  quantum      │            │           │            │           │
 │  computing"   │            │           │            │           │
 │──────────────▶│            │           │            │           │
 │               │──REQUEST──▶│           │            │           │
 │               │            │──infer───┼────────────▶│           │
 │               │            │          │            │──generate──│
 │               │            │          │            │           │
 │               │            │◀─response┼────────────│           │
 │               │            │          │            │           │
 │               │            │──evaluate (multi-dim):│           │
 │               │            │  relevance:  0.80     │           │
│               │            │  clarity:    0.45  ← too technical
 │               │            │  accuracy:   0.90     │           │
 │               │            │  completeness: 0.75   │           │
│               │            │  tone:       0.50  ← inappropriate for target
 │               │            │  ─────────────────    │           │
 │               │            │  QUALITY SCORE: 0.65  │           │
 │               │            │          │            │           │
 │               │            │  score < 0.85 → REGENERATE        │
 │               │            │          │            │           │
 │               │            │──store───▶│            │           │
 │               │            │  (prompt, │            │           │
 │               │            │   output_v1,│          │           │
 │               │            │   score=0.65,│         │           │
 │               │            │   feedback= │          │           │
│               │            │   "too      │          │           │
│               │            │    technical")│        │           │
 │               │            │          │            │           │
 │               │            │──regen───┼────────────▶│           │
 │               │            │  prompt + │           │──generate──│
 │               │            │  context: │           │  (with     │
 │               │            │  "semplifica│          │  feedback  │
 │               │            │   for non- │          │  context)  │
│               │            │   experts" │          │           │
 │               │            │◀─response_v2──────────│           │
 │               │            │          │            │           │
 │               │            │──re-evaluate:         │           │
 │               │            │  QUALITY SCORE: 0.89  │  ✓ PASS   │
 │               │            │          │            │           │
 │               │◀──INFORM──│           │            │           │
 │◀──simplified──│  response  │           │            │           │
 │   response    │            │           │            │           │
 │               │            │           │            │           │
│ "👍 Great!"   │            │           │            │           │
 │──────────────▶│──────────▶│           │            │           │
 │               │            │──update──▶│            │           │
 │               │            │  mark as  │            │           │
 │               │            │  positive │            │           │
 │               │            │           │            │           │
 │               │            │──update───┼────────────┼──────────▶│
 │               │            │  embed corrected context           │
 │               │            │  update Knowledge Graph            │
 │               │            │  mark old chunks stale             │
```

**FIPA-ACL Communication in the fast loop:**
- `REQUEST`: Interface → Critic (forwarding query)
- `INFORM`: Critic → Interface (validated response)
- `CFP` (Call for Proposal): Critic → Magellano (regeneration with feedback)

### C.3.3 Critic Agent Metrics — Multi-Dimensional Evaluation

```rust
/// The Critic Agent evaluates every output on 5 dimensions
pub struct CriticEvaluation {
    pub relevance: f32,      // 0-1: relevance to the original query
    pub clarity: f32,        // 0-1: expository clarity, readability
    pub accuracy: f32,       // 0-1: technical/factual correctness
    pub completeness: f32,   // 0-1: topic coverage
    pub tone: f32,           // 0-1: appropriateness for the target audience
}

impl CriticEvaluation {
    /// Weighted quality score — configurable weights per domain
    pub fn quality_score(&self, weights: &CriticWeights) -> f32 {
        weights.relevance * self.relevance
        + weights.clarity * self.clarity
        + weights.accuracy * self.accuracy
        + weights.completeness * self.completeness
        + weights.tone * self.tone
    }
}

    /// Decision thresholds
pub struct QualityThresholds {
    pub excellent: f32,    // ≥ 0.85 → use output, store as positive sample
    pub acceptable: f32,   // 0.60-0.85 → use with feedback, attempt regeneration
    pub poor: f32,         // < 0.60 → mandatory regeneration
}

/// Pesi default (sum = 1.0)
pub struct CriticWeights {
    pub relevance: f32,      // 0.25
    pub clarity: f32,        // 0.25
    pub accuracy: f32,       // 0.25
    pub completeness: f32,   // 0.15
    pub tone: f32,           // 0.10
}
```

### C.3.4 Schema Feedback Buffer

```sql
-- Main table for the feedback buffer
CREATE TABLE feedback_sessions (
    session_id          UUID PRIMARY KEY,
    tenant_id           VARCHAR(64) NOT NULL,        -- per multi-tenancy
    user_id             VARCHAR(64) NOT NULL,
    
    -- Input/Output
    prompt_text         TEXT NOT NULL,
    generated_output_v1 JSONB NOT NULL,              -- first generation
    generated_output_v2 JSONB,                       -- after feedback loop (nullable)
    
    -- Valutazione
    critic_score        FLOAT NOT NULL,              -- 0.0-1.0 quality score
    critic_dimensions   JSONB NOT NULL,              -- {relevance, clarity, accuracy, ...}
    feedback_type       VARCHAR(20) NOT NULL,         -- 'implicit'|'explicit'|'critic'
    feedback_text       TEXT,                         -- explicit user feedback text (if any)
    quality_delta       FLOAT,                       -- improvement v2 vs v1
    
    -- Lifecycle
    timestamp           TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    processed           BOOLEAN DEFAULT FALSE,       -- nightly batch flag
    processed_at        TIMESTAMP WITH TIME ZONE,
    batch_id            UUID,                        -- which batch processed this record
    
    -- Indici per query batch
    INDEX idx_unprocessed (processed, critic_score) WHERE processed = FALSE,
    INDEX idx_tenant_time (tenant_id, timestamp)
);
```

### C.3.5 PHASE 2: Nightly Batch (QLoRA Fine-tuning)

```
SCHEDULER         FEEDBACK      DATASET        QLoRA        MAGELLANO     MODEL
(cron/trigger)    BUFFER        BUILDER        TRAINER      (Runtime)     ROUTER
 │                  │              │              │             │            │
 │ ══════════ TRIGGER CONDITIONS ══════════════════            │            │
 │  • 100+ unprocessed samples                                 │            │
 │  • OR 24h timeout since last batch                          │            │
 │  • OR manual admin trigger                                  │            │
 │                  │              │              │             │            │
 │──collect────────▶│              │              │             │            │
 │  unprocessed     │              │              │             │            │
 │  samples         │              │              │             │            │
 │◀──127 samples───│              │              │             │            │
 │                  │              │              │             │            │
 │──build_dataset──┼─────────────▶│              │             │            │
 │                  │   filter:    │              │             │            │
 │                  │   score≥0.7  │              │             │            │
 │                  │   85 samples │              │             │            │
 │                  │              │              │             │            │
 │                  │   format:    │              │             │            │
 │                  │   Alpaca     │              │             │            │
 │                  │   template   │              │             │            │
 │                  │              │              │             │            │
 │──train──────────┼──────────────┼─────────────▶│             │            │
 │                  │              │    QLoRA:    │             │            │
 │                  │              │    4-bit NF4 │             │            │
 │                  │              │    r=16      │             │            │
 │                  │              │    3 epochs  │             │            │
 │                  │              │    ~45 min   │             │            │
 │                  │              │    (Apple    │             │            │
 │                  │              │     Silicon) │             │            │
 │                  │              │              │             │            │
 │                  │              │◀──adapter────│             │            │
 │                  │              │  lora_v2.bin │             │            │
 │                  │              │  (~35MB)     │             │            │
 │                  │              │              │             │            │
 │──validate───────┼──────────────┼──────────────│             │            │
 │  A/B test:       │              │              │             │            │
 │  10 held-out     │              │              │             │            │
 │  samples         │              │              │             │            │
 │  v1 vs v2 score  │              │              │             │            │
 │                  │              │              │             │            │
 │  v2 > v1?        │              │              │             │            │
 │  YES → proceed   │              │              │             │            │
 │                  │              │              │             │            │
 │──merge_deploy───┼──────────────┼──────────────┼────────────▶│            │
 │                  │              │              │   1. Dequant │            │
 │                  │              │              │      NF4→BF16│           │
 │                  │              │              │   2. Merge:  │            │
 │                  │              │              │      W = W₀  │            │
 │                  │              │              │      + ΔW    │            │
 │                  │              │              │   3. Re-quant│            │
 │                  │              │              │      BF16→NF4│           │
 │                  │              │              │             │            │
 │                  │              │              │             │──hot_swap──▶│
 │                  │              │              │             │  zero       │
 │                  │              │              │             │  downtime   │
 │                  │              │              │             │  (vedi C.5) │
 │                  │              │              │             │            │
 │──mark_processed─▶│              │              │             │            │
 │  85 samples      │              │              │             │            │
 │  batch_id: UUID  │              │              │             │            │
```

### C.3.6 QLoRA Configuration

```rust
/// QLoRA configuration for nightly batch
pub struct QLoRAConfig {
    // Quantization
    pub load_in_4bit: bool,                 // true
    pub quant_type: QuantType,              // NF4 (NormalFloat4)
    pub compute_dtype: ComputeDtype,        // BFloat16
    pub double_quant: bool,                 // true (nested quantization)
    
    // LoRA
    pub rank: u32,                          // 16 (rank matrici A, B)
    pub alpha: f32,                         // 32.0 (scaling factor)
    pub target_modules: Vec<String>,        // ["q_proj", "k_proj", "v_proj", 
                                            //  "o_proj", "gate_proj", 
                                            //  "up_proj", "down_proj"]
    pub dropout: f32,                       // 0.1
    
    // Training
    pub epochs: u32,                        // 3
    pub batch_size: u32,                    // 4
    pub gradient_accumulation_steps: u32,   // 4 (effective batch = 16)
    pub learning_rate: f64,                 // 2e-4
    pub optimizer: String,                  // "paged_adamw_32bit"
    pub bf16: bool,                         // true
    pub gradient_checkpointing: bool,       // true (salva VRAM)
    
    // Validation
    pub holdout_samples: u32,               // 10 (per A/B test pre-deploy)
    pub min_improvement: f32,               // 0.05 (v2 must be ≥5% better than v1)
}
```

**Key parameters and rationale:**

| Parameter | Value | Rationale |
|-----------|--------|-----------|
| Rank (r) | 16 | Balance between expressiveness and efficiency. r=16 captures ~95% of the information useful for task adaptation |
| Alpha (α) | 32 | α/r = 2.0 — moderate scaling factor, avoids instability |
| NF4 | 4-bit | 4× memory reduction vs FP16. Magellano 3.3B: 6.6 GB FP16 → 1.7 GB NF4 |
| Double quant | true | Also quantizes the quantization constants: additional -0.4 GB savings |
| Target modules | 7 | All linear layers in attention + MLP. Only ~0.5% trainable parameters |
| Epochs | 3 | Sufficient for adaptation without overfitting on 85 samples |
| Gradient checkpointing | true | Reduces VRAM peak by ~60% at the cost of ~20% extra training time |

### C.3.7 Merge & Deploy (Hot-Swap)

```rust
/// Adapter → base model merge → deploy pipeline
pub struct AdapterMergeAndDeploy {
    model_router: Arc<ModelRouter>,
    checkpoint_manager: Arc<CheckpointManager>,
}

impl AdapterMergeAndDeploy {
    pub async fn merge_and_deploy(&self, adapter_path: &Path) -> Result<()> {
        // 1. Dequantize base weights: NF4 → BF16
        //    W_base_bf16 = dequantize_nf4(W_base_nf4)
        
        // 2. Compute LoRA delta: ΔW = B × A × (α/r)
        //    dove A ∈ R^{d×r}, B ∈ R^{r×d}, α=32, r=16
        //    ΔW has the same shape as W_base
        
        // 3. Merge: W_merged = W_base_bf16 + ΔW
        
        // 4. Re-quantize: W_merged_nf4 = quantize_nf4(W_merged)
        
        // 5. Hot-swap via Model Router (vedi C.5)
        //    - Load W_merged_nf4 in standby instance
        //    - Health check
        //    - Switch traffic
        //    - Drain + unload old version
        
        // 6. Checkpoint: salva adapter + config per rollback
        self.checkpoint_manager.save_adapter(adapter_path, "lora_v2").await?;
        
        Ok(())
    }
}
```

### C.3.8 Complete Cycle (Day Cycle)

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  DAY 1 (Interactions — Fast Loop)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  User → Query → Magellano(v1.0) → Response
    ↓                                  ↓
  Feedback (👍/👎/implicit)     Critic Score
    ↓                                  ↓
  Vector Store updated            Feedback Buffer
  KG updated                      [accumula 100+ samples]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  NIGHT (Batch — Slow Loop)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Buffer → Filter(score≥0.7) → 85 samples → Alpaca format
    ↓
  QLoRA Training (3 epochs, ~45 min su Apple Silicon)
    ↓
  Adapter lora_v2.bin (~35MB)
    ↓
  A/B Validation (10 holdout samples)
    ↓
  v2 score > v1 + 5%? → YES → Merge → Hot-Swap
                       → NO  → Discard, log, alert admin

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  DAY 2 (Updated Model)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

User → Query → Magellano(v1.1) → Response(improved!)
    ↓
  [The cycle repeats...]
```

### C.3.9 Architecture Advantages

| Aspect | Benefit | Detail |
|---------|-----------|-----------|
| Real-time | Immediate improvements | Vector Store + KG updated in-session |
| Persistent | Preference memory | QLoRA incorporates patterns into the base model |
| Efficient | Only ~0.5% trainable parameters | LoRA rank 16, 7 target modules |
| Memory | 4× RAM reduction | NF4 quantization: 6.6GB → 1.7GB |
| Zero-downtime | Hot-swap adapters | Traffic switch after health check (C.5) |
| Cost-effective | Nightly training | Checkpoint ~35MB, GPU idle time |
| Multi-tenant | Separable adapters | Each tenant can have a customized adapter |
| Rollback safe | A/B validation gate | Deploy only if improvement ≥5% |

### C.3.10 Learning Path Metrics

```
# Fast loop
aios_critic_score_distribution{task_type, quantile}
aios_regeneration_count_total{reason="low_score|explicit_feedback"}
aios_quality_delta{session_id}                    # improvement v2 vs v1
aios_feedback_buffer_size{tenant_id}

# Slow loop
aios_qlora_training_duration_seconds
aios_qlora_samples_used{batch_id}
aios_qlora_adapter_size_bytes
aios_qlora_ab_test_improvement{batch_id}          # % improvement over base
aios_qlora_deploy_count_total{outcome="deployed|discarded"}
aios_model_version_active{model="magellano-3.3b"} # current version number
```

### C.3.A [v5.1 Refinement]: Complete Learning Path — Real-time Feedback + Nightly QLoRA Batch

This section fully replaces the previous C.3, integrating the end-to-end continuous learning cycle —to-end.

### C.3.1 Overview Architetturale

AI OS implements a two-speed continuous learning system:

1. **Fast loop (real-time):** In-session feedback immediately updates the Vector Store and Knowledge Graph
2. **Slow loop (nightly batch):** Aggregated feedback generates a dataset for QLoRA fine-tuning of Magellano

```
┌──────────────────────────────────────────────────────────────────┐
│                    LEARNING ARCHITECTURE                          │
│                                                                   │
│  FAST LOOP (session)               SLOW LOOP (nightly)           │
│  ┌────────────────────┐           ┌────────────────────┐         │
│  │ User Query          │           │ Feedback Buffer    │         │
│  │      ↓              │           │ (100+ samples)     │         │
│  │ Magellano Response  │           │      ↓             │         │
│  │      ↓              │           │ Quality Filter     │         │
│  │ Critic Score        │           │ (score ≥ 0.7)      │         │
│  │      ↓              │           │      ↓             │         │
│  │ score < 0.85?       │           │ QLoRA Training     │         │
│  │  YES → Regenerate   │           │ (3 epochs, 4-bit)  │         │
│  │  NO  → Deliver      │           │      ↓             │         │
│  │      ↓              │           │ Merge Adapters     │         │
│  │ Store in Buffer     │           │      ↓             │         │
│  │ Update Vector Store │           │ Hot-Swap Deploy    │         │
│  │ Update KG           │           │      ↓             │         │
│  └────────────────────┘           │ Magellano v(N+1)   │         │
│                                    └────────────────────┘         │
└──────────────────────────────────────────────────────────────────┘
```

### C.3.2 PHASE 1: Interactive Session (Real-time Learning)

```
USER          INTERFACE    CRITIC       FEEDBACK    MAGELLANO    MEMORY
                                        BUFFER      (Runtime)
 │               │            │           │            │           │
 │ "Explain      │            │           │            │           │
 │  quantum      │            │           │            │           │
 │  computing"   │            │           │            │           │
 │──────────────▶│            │           │            │           │
 │               │──REQUEST──▶│           │            │           │
 │               │            │──infer───┼────────────▶│           │
 │               │            │          │            │──generate──│
 │               │            │          │            │           │
 │               │            │◀─response┼────────────│           │
 │               │            │          │            │           │
 │               │            │──evaluate (multi-dim):│           │
 │               │            │  relevance:  0.80     │           │
│               │            │  clarity:    0.45  ← too technical
 │               │            │  accuracy:   0.90     │           │
 │               │            │  completeness: 0.75   │           │
│               │            │  tone:       0.50  ← inappropriate for target
 │               │            │  ─────────────────    │           │
 │               │            │  QUALITY SCORE: 0.65  │           │
 │               │            │          │            │           │
 │               │            │  score < 0.85 → REGENERATE        │
 │               │            │          │            │           │
 │               │            │──store───▶│            │           │
 │               │            │  (prompt, │            │           │
 │               │            │   output_v1,│          │           │
 │               │            │   score=0.65,│         │           │
 │               │            │   feedback= │          │           │
│               │            │   "too      │          │           │
│               │            │    technical")│        │           │
 │               │            │          │            │           │
 │               │            │──regen───┼────────────▶│           │
 │               │            │  prompt + │           │──generate──│
 │               │            │  context: │           │  (with     │
 │               │            │  "semplifica│          │  feedback  │
 │               │            │   for non- │          │  context)  │
│               │            │   experts" │          │           │
 │               │            │◀─response_v2──────────│           │
 │               │            │          │            │           │
 │               │            │──re-evaluate:         │           │
 │               │            │  QUALITY SCORE: 0.89  │  ✓ PASS   │
 │               │            │          │            │           │
 │               │◀──INFORM──│           │            │           │
 │◀──simplified──│  response  │           │            │           │
 │   response    │            │           │            │           │
 │               │            │           │            │           │
│ "👍 Great!"   │            │           │            │           │
 │──────────────▶│──────────▶│           │            │           │
 │               │            │──update──▶│            │           │
 │               │            │  mark as  │            │           │
 │               │            │  positive │            │           │
 │               │            │           │            │           │
 │               │            │──update───┼────────────┼──────────▶│
 │               │            │  embed corrected context           │
 │               │            │  update Knowledge Graph            │
 │               │            │  mark old chunks stale             │
```

**FIPA-ACL Communication in the fast loop:**
- `REQUEST`: Interface → Critic (inoltro query)
- `INFORM`: Critic → Interface (validated response)
- `CFP` (Call for Proposal): Critic → Magellano (regeneration with feedback)

### C.3.3 Critic Agent Metrics — Multi-Dimensional Evaluation

```rust
/// The Critic Agent evaluates every output on 5 dimensions
pub struct CriticEvaluation {
    pub relevance: f32,      // 0-1: relevance to the original query
    pub clarity: f32,        // 0-1: expository clarity, readability
    pub accuracy: f32,       // 0-1: technical/factual correctness
    pub completeness: f32,   // 0-1: topic coverage
    pub tone: f32,           // 0-1: appropriateness for the target audience
}

impl CriticEvaluation {
    /// Weighted quality score — configurable weights per domain
    pub fn quality_score(&self, weights: &CriticWeights) -> f32 {
        weights.relevance * self.relevance
        + weights.clarity * self.clarity
        + weights.accuracy * self.accuracy
        + weights.completeness * self.completeness
        + weights.tone * self.tone
    }
}

    /// Decision thresholds
pub struct QualityThresholds {
    pub excellent: f32,    // ≥ 0.85 → use output, store as positive sample
    pub acceptable: f32,   // 0.60-0.85 → use with feedback, attempt regeneration
    pub poor: f32,         // < 0.60 → mandatory regeneration
}

/// default weights (sum = 1.0)
pub struct CriticWeights {
    pub relevance: f32,      // 0.25
    pub clarity: f32,        // 0.25
    pub accuracy: f32,       // 0.25
    pub completeness: f32,   // 0.15
    pub tone: f32,           // 0.10
}
```

### C.3.4 Schema Feedback Buffer

```sql
-- Main table for the feedback buffer
CREATE TABLE feedback_sessions (
    session_id          UUID PRIMARY KEY,
    tenant_id           VARCHAR(64) NOT NULL,        -- per multi-tenancy
    user_id             VARCHAR(64) NOT NULL,
    
    -- Input/Output
    prompt_text         TEXT NOT NULL,
    generated_output_v1 JSONB NOT NULL,              -- first generation
    generated_output_v2 JSONB,                       -- after feedback loop (nullable)
    
    -- Evaluation
    critic_score        FLOAT NOT NULL,              -- 0.0-1.0 quality score
    critic_dimensions   JSONB NOT NULL,              -- {relevance, clarity, accuracy, ...}
    feedback_type       VARCHAR(20) NOT NULL,         -- 'implicit'|'explicit'|'critic'
    feedback_text       TEXT,                         -- explicit user feedback text (if any)
    quality_delta       FLOAT,                       -- improvement v2 vs v1
    
    -- Lifecycle
    timestamp           TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    processed           BOOLEAN DEFAULT FALSE,       -- nightly batch flag
    processed_at        TIMESTAMP WITH TIME ZONE,
    batch_id            UUID,                        -- which batch processed this record
    
    -- Indexes for query batch
    INDEX idx_unprocessed (processed, critic_score) WHERE processed = FALSE,
    INDEX idx_tenant_time (tenant_id, timestamp)
);
```

### C.3.5 PHASE 2: Nightly Batch (QLoRA Fine-tuning)

```
SCHEDULER         FEEDBACK      DATASET        QLoRA        MAGELLANO     MODEL
(cron/trigger)    BUFFER        BUILDER        TRAINER      (Runtime)     ROUTER
 │                  │              │              │             │            │
 │ ══════════ TRIGGER CONDITIONS ══════════════════            │            │
 │  • 100+ unprocessed samples                                 │            │
 │  • OR 24h timeout since last batch                          │            │
 │  • OR manual admin trigger                                  │            │
 │                  │              │              │             │            │
 │──collect────────▶│              │              │             │            │
 │  unprocessed     │              │              │             │            │
 │  samples         │              │              │             │            │
 │◀──127 samples───│              │              │             │            │
 │                  │              │              │             │            │
 │──build_dataset──┼─────────────▶│              │             │            │
 │                  │   filter:    │              │             │            │
 │                  │   score≥0.7  │              │             │            │
 │                  │   85 samples │              │             │            │
 │                  │              │              │             │            │
 │                  │   format:    │              │             │            │
 │                  │   Alpaca     │              │             │            │
 │                  │   template   │              │             │            │
 │                  │              │              │             │            │
 │──train──────────┼──────────────┼─────────────▶│             │            │
 │                  │              │    QLoRA:    │             │            │
 │                  │              │    4-bit NF4 │             │            │
 │                  │              │    r=16      │             │            │
 │                  │              │    3 epochs  │             │            │
 │                  │              │    ~45 min   │             │            │
 │                  │              │    (Apple    │             │            │
 │                  │              │     Silicon) │             │            │
 │                  │              │              │             │            │
 │                  │              │◀──adapter────│             │            │
 │                  │              │  lora_v2.bin │             │            │
 │                  │              │  (~35MB)     │             │            │
 │                  │              │              │             │            │
 │──validate───────┼──────────────┼──────────────│             │            │
 │  A/B test:       │              │              │             │            │
 │  10 held-out     │              │              │             │            │
 │  samples         │              │              │             │            │
 │  v1 vs v2 score  │              │              │             │            │
 │                  │              │              │             │            │
 │  v2 > v1?        │              │              │             │            │
 │  YES → proceed   │              │              │             │            │
 │                  │              │              │             │            │
 │──merge_deploy───┼──────────────┼──────────────┼────────────▶│            │
 │                  │              │              │   1. Dequant │            │
 │                  │              │              │      NF4→BF16│           │
 │                  │              │              │   2. Merge:  │            │
 │                  │              │              │      W = W₀  │            │
 │                  │              │              │      + ΔW    │            │
 │                  │              │              │   3. Re-quant│            │
 │                  │              │              │      BF16→NF4│           │
 │                  │              │              │             │            │
 │                  │              │              │             │──hot_swap──▶│
 │                  │              │              │             │  zero       │
 │                  │              │              │             │  downtime   │
 │                  │              │              │             │  (vedi C.5) │
 │                  │              │              │             │            │
 │──mark_processed─▶│              │              │             │            │
 │  85 samples      │              │              │             │            │
 │  batch_id: UUID  │              │              │             │            │
```

### C.3.6 QLoRA Configuration

```rust
/// QLoRA configuration for nightly batch
pub struct QLoRAConfig {
    // Quantization
    pub load_in_4bit: bool,                 // true
    pub quant_type: QuantType,              // NF4 (NormalFloat4)
    pub compute_dtype: ComputeDtype,        // BFloat16
    pub double_quant: bool,                 // true (nested quantization)
    
    // LoRA
    pub rank: u32,                          // 16 (rank matrici A, B)
    pub alpha: f32,                         // 32.0 (scaling factor)
    pub target_modules: Vec<String>,        // ["q_proj", "k_proj", "v_proj", 
                                            //  "o_proj", "gate_proj", 
                                            //  "up_proj", "down_proj"]
    pub dropout: f32,                       // 0.1
    
    // Training
    pub epochs: u32,                        // 3
    pub batch_size: u32,                    // 4
    pub gradient_accumulation_steps: u32,   // 4 (effective batch = 16)
    pub learning_rate: f64,                 // 2e-4
    pub optimizer: String,                  // "paged_adamw_32bit"
    pub bf16: bool,                         // true
    pub gradient_checkpointing: bool,       // true (salva VRAM)
    
    // Validation
    pub holdout_samples: u32,               // 10 (per A/B test pre-deploy)
    pub min_improvement: f32,               // 0.05 (v2 must be ≥5% better than v1)
}
```

**Key parameters and rationale:**

| Parameter | Value | Rationale |
|-----------|--------|-----------|
| Rank (r) | 16 | Balance between expressiveness and efficiency. r=16 captures ~95% of the information useful for task adaptation |
| Alpha (α) | 32 | α/r = 2.0 — moderate scaling factor, avoids instability |
| NF4 | 4-bit | 4× memory reduction vs FP16. Magellano 3.3B: 6.6 GB FP16 → 1.7 GB NF4 |
| Double quant | true | Also quantizes the quantization constants: additional -0.4 GB savings |
| Target modules | 7 | All linear layers in attention + MLP. Only ~0.5% trainable parameters |
| Epochs | 3 | Sufficient for adaptation without overfitting on 85 samples |
| Gradient checkpointing | true | Reduces VRAM peak by ~60% at the cost of ~20% extra training time |

### C.3.7 Merge & Deploy (Hot-Swap)

```rust
/// Adapter → base model merge → deploy pipeline
pub struct AdapterMergeAndDeploy {
    model_router: Arc<ModelRouter>,
    checkpoint_manager: Arc<CheckpointManager>,
}

impl AdapterMergeAndDeploy {
    pub async fn merge_and_deploy(&self, adapter_path: &Path) -> Result<()> {
        // 1. Dequantize base weights: NF4 → BF16
        //    W_base_bf16 = dequantize_nf4(W_base_nf4)
        
        // 2. Compute LoRA delta: ΔW = B × A × (α/r)
        //    dove A ∈ R^{d×r}, B ∈ R^{r×d}, α=32, r=16
        //    ΔW has the same shape as W_base
        
        // 3. Merge: W_merged = W_base_bf16 + ΔW
        
        // 4. Re-quantize: W_merged_nf4 = quantize_nf4(W_merged)
        
        // 5. Hot-swap via Model Router (vedi C.5)
        //    - Load W_merged_nf4 in standby instance
        //    - Health check
        //    - Switch traffic
        //    - Drain + unload old version
        
        // 6. Checkpoint: salva adapter + config per rollback
        self.checkpoint_manager.save_adapter(adapter_path, "lora_v2").await?;
        
        Ok(())
    }
}
```

### C.3.8 Complete Cycle (Day Cycle)

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  DAY 1 (Interactions — Fast Loop)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  User → Query → Magellano(v1.0) → Response
    ↓                                  ↓
  Feedback (👍/👎/implicit)     Critic Score
    ↓                                  ↓
  Vector Store updated            Feedback Buffer
  KG updated                      [accumula 100+ samples]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  NIGHT (Batch — Slow Loop)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Buffer → Filter(score≥0.7) → 85 samples → Alpaca format
    ↓
  QLoRA Training (3 epochs, ~45 min su Apple Silicon)
    ↓
  Adapter lora_v2.bin (~35MB)
    ↓
  A/B Validation (10 holdout samples)
    ↓
  v2 score > v1 + 5%? → YES → Merge → Hot-Swap
                       → NO  → Discard, log, alert admin

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  DAY 2 (Updated Model)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

User → Query → Magellano(v1.1) → Response(improved!)
    ↓
  [The cycle repeats...]
```

### C.3.9 Architecture Advantages

| Aspect | Benefit | Detail |
|---------|-----------|-----------|
| Real-time | Immediate improvements | Vector Store + KG updated in-session |
| Persistent | Preference memory | QLoRA incorporates patterns into the base model |
| Efficient | Only ~0.5% trainable parameters | LoRA rank 16, 7 target modules |
| Memory | 4× RAM reduction | NF4 quantization: 6.6GB → 1.7GB |
| Zero-downtime | Hot-swap adapters | Traffic switch after health check (C.5) |
| Cost-effective | Nightly training | Checkpoint ~35MB, GPU idle time |
| Multi-tenant | Separable adapters | Each tenant can have a customized adapter |
| Rollback safe | A/B validation gate | Deploy only if improvement ≥5% |

### C.3.10 Learning Path Metrics

```
# Fast loop
aios_critic_score_distribution{task_type, quantile}
aios_regeneration_count_total{reason="low_score|explicit_feedback"}
aios_quality_delta{session_id}                    # improvement v2 vs v1
aios_feedback_buffer_size{tenant_id}

# Slow loop
aios_qlora_training_duration_seconds
aios_qlora_samples_used{batch_id}
aios_qlora_adapter_size_bytes
aios_qlora_ab_test_improvement{batch_id}          # % improvement over base
aios_qlora_deploy_count_total{outcome="deployed|discarded"}
aios_model_version_active{model="magellano-3.3b"} # current version number
```

---

---


### C.4 Multi-Agent Collaboration — Negotiation via Consensus

```
PLANNER        REGISTRY       EXEC_DATA    EXEC_VIZ    EXEC_REPORT   CONSENSUS
 │               │               │            │            │            │
 │──find_agents──▶│               │            │            │            │
 │  skills:       │               │            │            │            │
 │  [data,viz,    │               │            │            │            │
 │   reporting]   │               │            │            │            │
 │◀──candidates──│               │            │            │            │
 │  [E_D, E_V,   │               │            │            │            │
 │   E_R]        │               │            │            │            │
 │               │               │            │            │            │
 │──PROPOSE──────┼──────────────▶│            │            │            │
 │  {task,budget, │              │            │            │            │
 │   deadline}    │              │            │            │            │
 │──PROPOSE──────┼──────────────┼───────────▶│            │            │
 │──PROPOSE──────┼──────────────┼────────────┼───────────▶│            │
 │               │               │            │            │            │
 │◀──AGREE───────┼──────────────│            │            │            │
 │  {can_do,      │              │            │            │            │
 │   est: 2s}     │              │            │            │            │
 │◀──AGREE───────┼──────────────┼────────────│            │            │
 │◀──REFUSE──────┼──────────────┼────────────┼────────────│            │
 │  {overloaded}  │              │            │            │            │
 │               │               │            │            │            │
 │──find_alt─────▶│               │            │            │            │
 │  skill:report  │               │            │            │            │
 │◀──EXEC_RPT_2──│               │            │            │            │
 │               │               │            │            │            │
 │──PROPOSE──────┼──────────────┼────────────┼────────────┼──────────▶│
 │  form_team:    │              │            │            │  EXEC_R2   │
 │  [E_D, E_V,   │              │            │            │            │
 │   E_R2]       │              │            │            │            │
 │◀──AGREE───────┼──────────────┼────────────┼────────────┼──────────│
 │               │               │            │            │            │
 │══ TEAM FORMED: EXECUTE PIPELINE ═══════════════════════│            │
 │               │               │            │            │            │
 │──REQUEST──────┼──────────────▶│            │            │            │
 │  "analyze Q3"  │              │─execute────│            │            │
 │               │               │            │            │            │
 │◀──INFORM──────┼──────────────│            │            │            │
 │  {data_result} │              │            │            │            │
 │               │               │            │            │            │
 │──REQUEST──────┼──────────────┼───────────▶│            │            │
 │  "chart data"  │              │  ──shared──▶│           │            │
 │               │               │   tensors  │            │            │
 │◀──INFORM──────┼──────────────┼────────────│            │            │
 │  {chart_handle}│              │            │            │            │
 │               │               │            │            │            │
 │──REQUEST(E_R2)┼──────────────┼────────────┼──────────▶│            │
 │  "gen report"  │              │            │           │            │
 │◀──INFORM──────┼──────────────┼────────────┼───────────│            │
 │  {pdf_handle}  │              │            │            │            │
 │               │               │            │            │            │
 │──CANCEL───────┼──────────────▶│───────────▶│──────────▶│            │
 │  "team done"   │              │            │            │            │
```

**FIPA-ACL performatives used:** PROPOSE, AGREE, REFUSE, REQUEST, INFORM, CANCEL

---


### C.5 Model Hot-Swap — LLM Update Without Downtime

```
ADMIN          MODEL_ROUTER    MAGELLANO_3.3B   MAGELLANO_3.3B_v2   STATE_AGENT
 │               │               │ (active)       │ (standby)         │
 │──hot_swap─────▶│               │                │                   │
 │  {new_adapter:  │              │                │                   │
 │   lora_v2.bin}  │              │                │                   │
 │               │               │                │                   │
 │               │──checkpoint──▶│                │                   │
 │               │               │──save_state────┼───────────────────▶│
 │               │               │  kv_cache,     │                   │ persist
 │               │               │  session_ctx   │                   │
 │               │               │                │                   │
 │               │──load_model───┼───────────────▶│                   │
 │               │               │                │──init             │
 │               │               │                │──load_base        │
 │               │               │                │──load_adapter     │
 │               │               │                │  (lora_v2.bin)    │
 │               │               │                │                   │
 │               │──health_check─┼───────────────▶│                   │
 │               │               │                │◀──OK──            │
 │               │               │                │                   │
 │               │──restore_state┼───────────────▶│                   │
 │               │               │                │◀─────────────────│
 │               │               │                │  kv_cache loaded  │
 │               │               │                │                   │
 │               │══ SWITCH TRAFFIC ══════════════│                   │
 │               │  route: v2    │                │                   │
 │               │               │                │                   │
 │               │──drain────────▶│               │                   │
 │               │  (wait for    │ finish         │                   │
 │               │   in-flight)  │ pending        │                   │
 │               │               │                │                   │
 │               │──unload───────▶│               │                   │
 │               │               │ free memory    │                   │
 │               │               │                │                   │
 │◀──complete────│               │                │ (now active)      │
 │  swap time:   │               │                │                   │
 │  ~2.3s        │               │                │                   │
```

**Garanzie:**
- **Zero request loss** — traffic switch only after v2 health check passes
- **State preservation** — KV cache and session context transferred via State Agent
- **Rollback** — if v2 health check fails, v1 remains active
- **Drain period** — in-flight requests on v1 complete before unload
- **Estimated time** — ~2–3 s for full swap (load adapter + restore state)

---



ewpage

---

## v5.1 Changelog

| Section | Type | Rationale |
|---------|------|-------------|
| C.1 metrics | **ADDED** | Per-component timing breakdown (Kimi review: times not detailed) |
| C.2 diagrams | **EXPANDED** | 3 distributed error scenarios: partition, split-brain, crash+checkpoint |
| C.2 retry policy | **REFINED** | Max retry 3 (was 2), formal escalation policies, backoff strategies |
| C.2 metrics | **ADDED** | 8 error recovery metrics for observability |
| C.3 complete | **REWRITTEN** | E2E learning path architecture with fast/slow loop |
| C.3.3 | **NEW** | Multi-dimensional Critic evaluation (5 weighted dimensions) |
| C.3.4 | **NEW** | Feedback Buffer SQL schema with indices for batch queries |
| C.3.5 | **NEW** | Complete nightly batch sequence diagram |
| C.3.6 | **NEW** | QLoRA configuration with rationale for each parameter |
| C.3.7 | **NEW** | Merge & Deploy pipeline (NF4→BF16→merge→NF4→hot-swap) |
| C.3.8 | **NEW** | Day Cycle diagram (fast loop → slow loop → deploy) |
| C.3.9 | **NEW** | Architecture advantages table (8 aspects) |
| C.3.10 | **NEW** | Prometheus metrics for fast and slow loops |


# Part II — API Contracts and Data Model

## PART D: gRPC API CONTRACTS — PROTOBUF DEFINITIONS

### D.1 3-Bus Architecture

AI OS uses 3 distinct communication buses, each optimized for a specific type of traffic. This separation is critical: mixing control traffic with tensor transfers would cause head-of-line blocking and unpredictable latencies.

```
┌─────────────────────────────────────────────────────────────────┐
│                    APPLICATION LAYER                             │
│    Macro-Agents (FIPA-ACL semantics via performatives)          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  BUS 1: CONTROL          BUS 2: DATA            BUS 3: TENSORS │
│  gRPC + Protobuf         NATS + JSON-RPC 2.0    Shared Memory  │
│  Latency: 1-10ms         Latency: 10-100ms      Latency: <1µs  │
│  Throughput: basso        Throughput: medio       Throughput: max │
│  Pattern: req/rep,        Pattern: pub/sub,       Pattern: ring  │
│  bi-di stream             fan-out                 buffer, DMA    │
│                                                                 │
│  Use: task dispatch,      Use: risultati API,     Use: embeddings│
│  agent lifecycle,         metadata, logs          KV-cache, model│
│  health, consensus        structured, events     weights, stream│
└─────────────────────────────────────────────────────────────────┘
```

### D.2 Bus 1: Control (gRPC + Protobuf)

The control bus handles all strategic interactions between Macro-Agents and coordination with Meso-Agents. It uses gRPC bidirectional streaming in order to support multi-turn conversations.

#### D.2.1 Common Types

```protobuf
syntax = "proto3";
package aios.common;

import "google/protobuf/timestamp.proto";
import "google/protobuf/duration.proto";
import "google/protobuf/any.proto";

// === AGENT IDENTITY ===

message AgentId {
  string tier = 1;          // "macro", "meso", "micro"
  string type = 2;          // "planner", "executor", "critic", "memory", "interface"
  string instance_id = 3;   // "001", "0x7F3A2B00"
  string zone = 4;          // "global", "zone-eu", "numa-0"
}

// === FIPA-ACL PERFORMATIVES ===

enum Performative {
  PERFORMATIVE_UNSPECIFIED = 0;
  REQUEST = 1;
  INFORM = 2;
  PROPOSE = 3;
  ACCEPT_PROPOSAL = 4;
  REJECT_PROPOSAL = 5;
  AGREE = 6;
  REFUSE = 7;
  CANCEL = 8;
  FAILURE = 9;
  QUERY_IF = 10;
  QUERY_REF = 11;
  CONFIRM = 12;
  NOT_UNDERSTOOD = 13;
}

// === QoS ===

enum QosClass {
  QOS_UNSPECIFIED = 0;
  REALTIME = 1;       // <50ms, critical inference
  INTERACTIVE = 2;    // <500ms, task utente
  BULK = 3;           // best-effort, batch processing
}

message QualityOfService {
  QosClass qos_class = 1;
  google.protobuf.Duration max_latency = 2;
  uint32 max_retries = 3;
  google.protobuf.Duration retry_backoff = 4;
}

// === CONVERSATION CONTEXT ===

message ConversationContext {
  string conversation_id = 1;   // UUID
  string thread_id = 2;         // per multi-thread dentro una conversazione
  string parent_message_id = 3; // per reply chains
  uint64 sequence_number = 4;   // ordinamento
}

// === SECURITY ENVELOPE ===

message SecurityEnvelope {
  bytes signature = 1;         // ED25519
  string encryption = 2;       // "aes-256-gcm" o "none"
  bytes nonce = 3;
  string certificate_ref = 4;  // reference to the X.509 cert in the registry
}

// === GENERIC MESSAGE WRAPPER ===

message AgentMessage {
  string message_id = 1;                         // UUID
  AgentId sender = 2;
  AgentId receiver = 3;
  Performative performative = 4;
  ConversationContext context = 5;
  QualityOfService qos = 6;
  SecurityEnvelope security = 7;
  google.protobuf.Timestamp timestamp = 8;
  google.protobuf.Any payload = 9;               // service-specific payload type
  map<string, string> metadata = 10;             // headers custom
}
```

#### D.2.2 Task Orchestration Service

```protobuf
syntax = "proto3";
package aios.orchestration;

import "aios/common.proto";
import "google/protobuf/timestamp.proto";

// === TASK DEFINITION ===

message TaskSpec {
  string task_id = 1;
  string action = 2;                    // "analyze_sales", "generate_code", "validate_output"
  map<string, string> parameters = 3;
    uint32 priority = 4;                  // 0-10, 10 = maximum
  google.protobuf.Timestamp deadline = 5;
  repeated string required_skills = 6;  // skills required by the executor
  repeated string dependencies = 7;     // task_ids this task depends on (DAG edges)
  ResourceEstimate resources = 8;
}

message ResourceEstimate {
  uint64 estimated_tokens = 1;
  uint64 estimated_memory_bytes = 2;
  google.protobuf.Duration estimated_duration = 3;
    string preferred_model = 4;           // "magellano-3.3b", "magellano-77m", "cloud"
}

// === TASK DAG ===

message TaskDAG {
  string dag_id = 1;
  string goal_description = 2;
  repeated TaskSpec tasks = 3;          // DAG nodes
  // dependencies are embedded inside TaskSpec.dependencies
  google.protobuf.Timestamp created_at = 4;
  aios.common.AgentId planner = 5;     // agent that generated the DAG
}

// === TASK RESULT ===

message TaskResult {
  string task_id = 1;
  TaskStatus status = 2;
    google.protobuf.Any output = 3;      // typed result
  float quality_score = 4;             // 0.0-1.0, from the Critic
  string error_message = 5;
  google.protobuf.Duration execution_time = 6;
  repeated string artifacts = 7;       // URI a file/tensor prodotti
}

enum TaskStatus {
  TASK_UNSPECIFIED = 0;
  PENDING = 1;
  RUNNING = 2;
  COMPLETED = 3;
  FAILED = 4;
  CANCELLED = 5;
  RETRYING = 6;
}

// === SERVICE DEFINITION ===

service OrchestratorService {
    // Planner → Orchestrator: submit a DAG of tasks
  rpc SubmitDAG(TaskDAG) returns (SubmitDAGResponse);
  
    // Orchestrator → Executor: assign task (bidirectional streaming for progress)
  rpc ExecuteTask(stream TaskExecutionMessage) returns (stream TaskExecutionMessage);
  
  // Any agent → Orchestrator: query task state
  rpc GetTaskStatus(TaskStatusRequest) returns (TaskResult);
  
  // Orchestrator → all: lifecycle notifications (server-side stream)
  rpc SubscribeEvents(EventSubscription) returns (stream OrchestratorEvent);
  
  // Planner → Orchestrator: replan after failure
  rpc ReplanDAG(ReplanRequest) returns (TaskDAG);
}

message SubmitDAGResponse {
  string dag_id = 1;
  uint32 estimated_tasks = 2;
  google.protobuf.Duration estimated_total_time = 3;
}

message TaskExecutionMessage {
  oneof content {
    TaskSpec assignment = 1;        // orchestrator → executor: assegnazione
    TaskProgress progress = 2;      // executor → orchestrator: progresso
    TaskResult result = 3;          // executor → orchestrator: risultato finale
    TaskCancel cancel = 4;          // orchestrator → executor: annulla
  }
}

message TaskProgress {
  string task_id = 1;
  float progress_pct = 2;          // 0.0-1.0
  string status_message = 3;
  uint64 tokens_generated = 4;
}

message TaskCancel {
  string task_id = 1;
  string reason = 2;
}

message TaskStatusRequest {
  string task_id = 1;
}

message EventSubscription {
  repeated string event_types = 1;  // ["task.completed", "agent.failed", "dag.finished"]
  aios.common.AgentId subscriber = 2;
}

message OrchestratorEvent {
  string event_type = 1;
  google.protobuf.Timestamp timestamp = 2;
  google.protobuf.Any payload = 3;
}

message ReplanRequest {
  string original_dag_id = 1;
  string failed_task_id = 2;
  string failure_reason = 3;
  repeated TaskResult completed_results = 4;  // risultati già ottenuti
}
```

#### D.2.3 Inference Service (via HAL)

```protobuf
syntax = "proto3";
package aios.inference;

import "aios/common.proto";

// === INFERENCE REQUEST/RESPONSE ===

message InferenceRequest {
  string request_id = 1;
  aios.common.AgentId requester = 2;
    string model_id = 3;              // "magellano-3.3b", "magellano-77m", "llama-cpp-q4"
  oneof input {
    TextInput text = 4;
    EmbeddingInput embedding = 5;
  }
  InferenceOptions options = 6;
}

message TextInput {
  string prompt = 1;
  repeated Message conversation_history = 2;
  uint32 max_tokens = 3;
  float temperature = 4;
  float top_p = 5;
  repeated string stop_sequences = 6;
}

message Message {
  string role = 1;     // "system", "user", "assistant"
  string content = 2;
}

message EmbeddingInput {
  string text = 1;
  string model_variant = 2;   // quale layer usare per embeddings
}

message InferenceOptions {
  bool stream = 1;
  string routing_policy = 2;  // "local_first", "task_adaptive", "power_aware"
  uint32 timeout_ms = 3;
}

message InferenceResponse {
  string request_id = 1;
  oneof result {
    TextOutput text = 2;
    EmbeddingOutput embedding = 3;
    InferenceError error = 4;
  }
  InferenceMetrics metrics = 5;
}

message TextOutput {
  string content = 1;
  uint32 tokens_generated = 2;
  string finish_reason = 3;    // "stop", "max_tokens", "timeout"
    string model_used = 4;       // which backend actually served the request
}

message EmbeddingOutput {
  repeated float vector = 1;
  uint32 dimensions = 2;
  string model_used = 3;
}

message InferenceError {
  string code = 1;
  string message = 2;
    string fallback_model = 3;   // suggestion for retry
}

message InferenceMetrics {
  uint32 tokens_per_second = 1;
  uint32 time_to_first_token_ms = 2;
  uint32 total_latency_ms = 3;
  string backend_used = 4;     // "magellano", "llama-cpp", "vllm", "cloud"
  float gpu_utilization = 5;
  uint64 memory_used_bytes = 6;
}

// === STREAMING TOKEN ===

message TokenStreamChunk {
  string request_id = 1;
  string token = 2;
  uint32 token_index = 3;
  bool is_final = 4;
  InferenceMetrics metrics = 5;  // present only when is_final=true
}

// === MODEL MANAGEMENT ===

message ModelInfo {
  string model_id = 1;
  string backend = 2;           // "magellano", "llama-cpp", "vllm", "remote"
  string version = 3;
  uint64 parameter_count = 4;
  uint32 max_context_length = 5;
  repeated string quantization = 6;  // ["FP16", "NF4", "Q4_K_M"]
  bool supports_streaming = 7;
  bool supports_embedding = 8;
  ModelHealth health = 9;
}

message ModelHealth {
  bool is_loaded = 1;
  float gpu_memory_pct = 2;
  uint32 active_requests = 3;
  uint32 avg_tokens_per_sec = 4;
}

// === SERVICE ===

service InferenceService {
  rpc Infer(InferenceRequest) returns (InferenceResponse);
  rpc InferStream(InferenceRequest) returns (stream TokenStreamChunk);
  rpc Embed(InferenceRequest) returns (InferenceResponse);
  rpc ListModels(ListModelsRequest) returns (ListModelsResponse);
  rpc LoadModel(LoadModelRequest) returns (ModelInfo);
  rpc UnloadModel(UnloadModelRequest) returns (UnloadModelResponse);
  rpc HotSwap(HotSwapRequest) returns (HotSwapResponse);
  rpc HealthCheck(HealthCheckRequest) returns (ModelHealth);
}

message ListModelsRequest {}
message ListModelsResponse { repeated ModelInfo models = 1; }
message LoadModelRequest { string model_id = 1; map<string, string> config = 2; }
message UnloadModelRequest { string model_id = 1; }
message UnloadModelResponse { bool success = 1; uint64 freed_bytes = 2; }
message HotSwapRequest {
  string current_model = 1;
  string new_adapter = 2;      // "lora_v2.bin"
  bool preserve_state = 3;
}
message HotSwapResponse {
  bool success = 1;
  uint32 swap_time_ms = 2;
  string active_model = 3;
}
message HealthCheckRequest { string model_id = 1; }
```

#### D.2.4 Agent Registry Service

```protobuf
syntax = "proto3";
package aios.registry;

import "aios/common.proto";
import "google/protobuf/timestamp.proto";

message AgentCapability {
  aios.common.AgentId agent_id = 1;
  string version = 2;
  repeated string skills = 3;       // ["code_generation", "data_analysis"]
  repeated string domains = 4;      // ["finance", "healthcare"]
  repeated string models = 5;       // ["magellano-3.3b"]
  repeated string protocols = 6;    // ["ioa/1.0", "a2a/1.0"]
  repeated string qos_classes = 7;  // ["realtime", "bulk"]
  AgentStatus status = 8;
  google.protobuf.Timestamp last_heartbeat = 9;
  uint32 ttl_seconds = 10;
  map<string, string> metadata = 11;
  AgentEndpoint endpoint = 12;
}

message AgentEndpoint {
  string grpc_address = 1;        // "agent-executor-001:50051"
  string shared_memory_key = 2;   // per tensori
  string nats_subject = 3;        // per pub/sub
}

enum AgentStatus {
  STATUS_UNSPECIFIED = 0;
  ACTIVE = 1;
  BUSY = 2;
  DRAINING = 3;
  OFFLINE = 4;
  FAILED = 5;
}

message CapabilityQuery {
  repeated string required_skills = 1;
  repeated string preferred_domains = 2;
  aios.common.QosClass min_qos = 3;
  uint32 max_results = 4;
    string semantic_query = 5;      // semantic search via embedding
}

service RegistryService {
  rpc Register(AgentCapability) returns (RegisterResponse);
  rpc Deregister(DeregisterRequest) returns (DeregisterResponse);
  rpc Heartbeat(HeartbeatRequest) returns (HeartbeatResponse);
  rpc FindAgents(CapabilityQuery) returns (FindAgentsResponse);
  rpc GetAgent(GetAgentRequest) returns (AgentCapability);
  rpc WatchAgents(WatchRequest) returns (stream AgentEvent);
}

message RegisterResponse { bool success = 1; string assigned_id = 2; }
message DeregisterRequest { aios.common.AgentId agent_id = 1; }
message DeregisterResponse { bool success = 1; }
message HeartbeatRequest {
  aios.common.AgentId agent_id = 1;
  AgentStatus status = 2;
  map<string, double> metrics = 3;  // "cpu_pct", "memory_pct", "active_tasks"
}
message HeartbeatResponse { bool acknowledged = 1; }
message FindAgentsResponse { repeated AgentCapability agents = 1; }
message GetAgentRequest { aios.common.AgentId agent_id = 1; }
message WatchRequest { repeated string event_types = 1; }
message AgentEvent {
  string event_type = 1;  // "registered", "deregistered", "status_changed", "failed"
  AgentCapability agent = 2;
  google.protobuf.Timestamp timestamp = 3;
}
```

#### D.2.5 Critic/Validation Service

```protobuf
syntax = "proto3";
package aios.critic;

import "aios/common.proto";

message ValidationRequest {
  string request_id = 1;
  string task_id = 2;
  google.protobuf.Any output_to_validate = 3;
  ValidationCriteria criteria = 4;
  aios.common.AgentId requester = 5;
}

message ValidationCriteria {
  float min_quality_score = 1;     // threshold, es. 0.8
  bool require_fact_check = 2;
  bool require_security_scan = 3;
  bool require_code_review = 4;
  string schema_ref = 5;           // JSON Schema for payload structure validation
  repeated string forbidden_patterns = 6;  // regex da rifiutare
}

message ValidationResult {
  string request_id = 1;
  ValidationVerdict verdict = 2;
  float quality_score = 3;         // 0.0-1.0
  repeated ValidationIssue issues = 4;
    string feedback = 5;             // structured feedback for improvement
  map<string, float> sub_scores = 6;  // "accuracy", "completeness", "security"
}

enum ValidationVerdict {
  VERDICT_UNSPECIFIED = 0;
  APPROVED = 1;
  APPROVED_WITH_WARNINGS = 2;
  REJECTED = 3;
  NEEDS_REVISION = 4;
}

message ValidationIssue {
  string category = 1;    // "security", "accuracy", "format", "performance"
  string severity = 2;    // "critical", "warning", "info"
  string description = 3;
  string suggestion = 4;
  string location = 5;    // location within the output
}

service CriticService {
  rpc Validate(ValidationRequest) returns (ValidationResult);
  rpc ValidateStream(stream ValidationRequest) returns (stream ValidationResult);
  rpc GetValidationHistory(ValidationHistoryRequest) returns (ValidationHistoryResponse);
}

message ValidationHistoryRequest { string task_id = 1; }
message ValidationHistoryResponse { repeated ValidationResult results = 1; }
```

### D.3 Bus 2: Structured Data (NATS + JSON-RPC 2.0)

Bus 2 uses NATS as transport and JSON-RPC 2.0 as message format. Protobuf is not required — the flexibility of JSON is preferred for heterogeneous data.

#### D.3.1 NATS Subject Hierarchy

```
aios.>                              # root namespace
aios.events.>                       # all events
aios.events.task.completed          # task completato
aios.events.task.failed             # task fallito
aios.events.agent.registered        # new agent registered
aios.events.agent.failed            # agent in error state
aios.events.model.loaded            # model loaded
aios.events.model.swapped           # hot-swap completato
aios.events.health.>                # heartbeat e health
aios.events.health.{agent_id}       # heartbeat specifico

aios.data.>                         # structured data
aios.data.results.{task_id}         # risultati task
aios.data.metrics.{agent_id}        # per-agent metrics
aios.data.logs.{agent_id}           # structured logs
aios.data.feedback.{conversation_id}  # feedback from the Critic

aios.control.>                      # commands (alternative to gRPC for fire-and-forget)
aios.control.broadcast              # broadcast messages to all agents
aios.control.{agent_type}.>         # messages by agent type
```

#### D.3.2 JSON-RPC 2.0 Message Format

```json
{
  "jsonrpc": "2.0",
  "id": "msg_a1b2c3d4",
  "method": "agent.task.inform",
  "params": {
    "protocol": "ioa/1.0",
    "sender": {
      "id": "macro.executor.001@global",
      "type": "executor"
    },
    "receiver": {
      "id": "macro.planner.001@global",
      "type": "planner"
    },
    "conversation": {
      "id": "conv_uuid",
      "thread": "thread_1",
      "sequence": 5
    },
    "semantic": {
      "performative": "inform",
      "ontology": "https://ai-os.org/ontology/task/v1",
      "content": {
        "@type": "TaskResult",
        "task_id": "task_analyze_sales",
        "status": "completed",
        "output": { "summary": "...", "charts": ["handle:tensor_001"] },
        "quality_score": 0.92
      }
    },
    "qos": {
      "class": "interactive",
      "max_latency_ms": 500
    }
  }
}
```

### D.4 Bus 3: Tensors e Stream (Shared Memory)

Bus 3 uses neither gRPC nor NATS — it operates directly on shared memory with a compact binary protocol for sub-microsecond latency.

#### D.4.1 Binary Message Header (Rust struct)

```rust
/// Binary message header for shared memory
/// Total overhead: 48 bytes
#[repr(C, packed)]
pub struct TensorMessageHeader {
    pub version: u8,            // 1
    pub message_type: u8,       // 0=tensor, 1=kv_cache, 2=checkpoint, 3=stream_chunk
    pub flags: u16,             // COMPRESSED, ENCRYPTED, ACK_REQUIRED
    pub conversation_id: u128,  // UUID
    pub sequence: u64,          // per stream ordering
    pub timestamp_nanos: u64,   // UNIX nanoseconds
    pub sender_hash: u32,       // hash of the agent ID (more compact than a string)
    pub receiver_hash: u32,     // idem
    pub content_type: u8,       // 0=f32, 1=f16, 2=bf16, 3=int8, 4=raw_bytes
    pub content_length: u32,    // payload size in bytes
    pub checksum: u32,          // CRC32
    pub _padding: [u8; 3],      // 48 bytes allignment
}
```

#### D.4.2 Tensor Handle Protocol

When an agent needs to send a tensor, it does not copy the data — it allocates in the shared memory pool and sends only a handle via Bus 1 o Bus 2.

```rust
/// Tensor handling in shared memory
pub struct TensorHandle {
    pub pool_id: u32,          // which pool
    pub offset: u64,           // byte offset within the pool
    pub length: u64,           // size in bytes
    pub shape: Vec<u64>,       // [batch, seq_len, hidden_dim]
    pub dtype: DataType,       // F32, F16, BF16, Int8
    pub fence_id: u64,         // fence for synchronization
}

/// Workflow:
/// 1. Executor allocates in the pool: handle = pool.allocate(size)
/// 2. Executor writes tensor: pool.write(handle, tensor_data)
/// 3. Executor signals fence: fence.signal(handle.fence_id)
/// 4. Executor sends handle via Bus 1: send(TensorHandleMessage { handle })
/// 5. Receiver wait for fence: fence.wait(handle.fence_id)
/// 6. Receiver reads tensore: data = pool.read(handle)
/// 7. Receiver release: pool.release(handle)
```

---

## PART E: DATA MODEL — GLOBAL STATE MANAGER

### E.1 Tiered Storage Architecture

The Global State Manager implements a 4-tier storage model, where data migrates automatically based on access frequency, size, and criticality.

```
┌─────────────────────────────────────────────────────────────────┐
│                       STATE ORCHESTRATOR                        │
│   Replicator · Consistency Checker · GC · Migration Engine      │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  L1: WORKING MEMORY          L2: VECTOR STORE                   │
│  Arc<RwLock<HashMap>>        FAISS/LanceDB                      │
│  TTL: session                TTL: permanent                     │
│  Latency: <1µs               Latency: 1-5ms                     │
│  Size: ~1 GB                 Size: ~4 GB                        │
│  Content:                    Content:                           │
│  - Active KV cache           - Dense embeddings (FAISS)         │
│  - Token buffer              - Sparse index (BM25)              │
│  - Conversation context       - Per-chunk metadata              │
│  - Variabili runtime         - Hybrid search reranking          │
│                                                                 │
│  L3: KNOWLEDGE GRAPH         L4: PERSISTENT STORE               │
│  Neo4j / in-memory graph     Redis (warm) + MongoDB (cold)      │
│  TTL: permanent              TTL: configurable                  │
│  Latency: 5-50ms             Latency: 1-100ms                   │
│  Size: ~2 GB                 Size: ~50 GB                       │
│  Content:                    Content:                           │
│  - Entities (NER)            - Agent checkpoints                │
│  - Relations (triplets)      - Operation journal                │
│  - Ontologie                 - Model artifacts                  │
│  - Inference rules           - Session history                  │
│  - Graph RAG traversals      - Audit trail                      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### E.2 Main Entity Schema

#### E.2.1 Session State

```rust
/// State of an active user session
pub struct SessionState {
    pub session_id: Uuid,
    pub user_id: String,
    pub created_at: DateTime<Utc>,
    pub last_active: DateTime<Utc>,
    pub ttl: Duration,
    
    // Conversation context
    pub conversation_history: Vec<ConversationTurn>,
    pub active_dag: Option<String>,        // current DAG ID
    pub pending_tasks: Vec<String>,        // task IDs
    
    // Preferenze runtime
    pub preferred_model: String,           // "magellano-3.3b"
    pub routing_policy: String,            // "local_first"
    pub language: String,                  // "it", "en"
    
    // KV Cache reference
    pub kv_cache_handle: Option<TensorHandle>,
}

pub struct ConversationTurn {
    pub turn_id: Uuid,
    pub role: String,          // "user", "assistant", "system"
    pub content: String,
    pub timestamp: DateTime<Utc>,
    pub tokens_used: u32,
    pub agent_id: String,      // which agent responded
    pub quality_score: Option<f32>,
}
```

#### E.2.2 Agent State (per checkpoint/restore)

```rust
/// Persistent agent state for checkpointing
pub struct AgentCheckpoint {
    pub agent_id: String,              // "macro.planner.001@global"
    pub checkpoint_id: String,
    pub timestamp: DateTime<Utc>,
    pub version: u32,
    
    // Serialized internal state
    pub state_data: HashMap<String, Vec<u8>>,   // key → bincode-serialized value
    pub state_size_bytes: u64,
    
    // Tensor references
    pub tensor_handles: Vec<TensorHandle>,
    
    // Metrics captured at checkpoint time
    pub metrics_snapshot: AgentMetrics,
}

pub struct AgentMetrics {
    pub tasks_completed: u64,
    pub tasks_failed: u64,
    pub avg_latency_ms: f64,
    pub avg_quality_score: f64,
    pub memory_used_bytes: u64,
    pub uptime_seconds: u64,
}
```

#### E.2.3 Vector Store Entry

```rust
/// Entry in the Vector Store (FAISS/LanceDB)
pub struct VectorEntry {
    pub entry_id: Uuid,
    pub source_document: String,    // URI of the source document
    pub chunk_index: u32,           // position within the document
    pub chunk_text: String,         // raw chunk text
    pub embedding: Vec<f32>,        // dense embedding vector (768 or 1024 dims)
    pub sparse_tokens: HashMap<String, f32>,  // BM25 token weights
    
    // Metadata for filtering
    pub metadata: VectorMetadata,
    
    // Lifecycle
    pub created_at: DateTime<Utc>,
    pub last_accessed: DateTime<Utc>,
    pub access_count: u64,
    pub is_stale: bool,             // marked stale by the Learning Path
}

pub struct VectorMetadata {
    pub domain: String,              // "finance", "code", "general"
    pub language: String,
    pub source_type: String,         // "document", "conversation", "feedback"
    pub tags: Vec<String>,
    pub confidence: f32,             // 0.0-1.0
    pub conversation_id: Option<String>,
}
```

#### E.2.4 Knowledge Graph Schema

```
    // Neo4j node types and relations

(:Entity {
    id: UUID,
    name: String,
    type: String,          // "person", "concept", "tool", "model", "task"
    description: String,
    embedding: [Float],    // per graph RAG
    created_at: DateTime,
    updated_at: DateTime,
    confidence: Float,     // 0.0-1.0
    source: String         // "extraction", "user_defined", "inference"
})

(:Entity)-[:RELATES_TO {
    relation_type: String,  // "uses", "depends_on", "similar_to", "part_of"
    weight: Float,          // relationship strength
    evidence: String,       // source from which this relation was extracted
    created_at: DateTime
}]->(:Entity)

    // Specific relations
(:Agent)-[:EXECUTED]->(:Task)
(:Task)-[:PRODUCED]->(:Artifact)
(:Task)-[:DEPENDS_ON]->(:Task)
(:Model)-[:SERVES]->(:Agent)
(:User)-[:OWNS]->(:Session)
(:Document)-[:CONTAINS]->(:Chunk)
(:Chunk)-[:EMBEDDED_AS]->(:VectorEntry)
```

#### E.2.5 Operation Journal (Exactly-Once Semantics)

```rust
/// Journal entry for exactly-once delivery and crash recovery
pub struct JournalEntry {
    pub entry_id: u64,             // auto-increment monotonic
    pub operation_id: Uuid,        // idempotency key
    pub timestamp: DateTime<Utc>,
    pub agent_id: String,
    pub operation_type: OperationType,
    pub target_key: String,        // key in the StateStore
    pub before_value: Option<Vec<u8>>,  // per rollback
    pub after_value: Option<Vec<u8>>,   // value written by the operation
    pub status: JournalStatus,
    pub superstep: u64,            // per checkpoint coordinato
}

pub enum OperationType {
    Set,
    Delete,
    CheckpointStart,
    CheckpointCommit,
    CheckpointAbort,
}

pub enum JournalStatus {
    Pending,
    Committed,
    RolledBack,
}
```

### E.3 Migration & Tiering Policies

```
POLICY: DATA TEMPERATURE
Hot  (L1, access >10/min)     → Working Memory (HashMap in-process)
Warm (L2-L3, access 1-10/min) → Redis + Vector Store
Cold (L4, access <1/min)      → MongoDB + File Store
Archive (access ~0)           → Compressed file, retrieved on demand only

POLICY: CHECKPOINT INTERVAL
Macro-agents: every 60 seconds or after 10 completed tasks
Meso-agents: every 300 seconds
Micro-agents: NOT checkpointed (stateless, recreatable)

POLICY: GARBAGE COLLECTION
Vector entries is_stale && last_accessed > 7 giorni  → delete
Journal entries status=Committed && age > 30 giorni  → archive
Inactive session KV cache > TTL              → evict
Checkpoint superseded by a more recent one           → delete (keep last 3)
```

---

## PART F: ARCHITECTURE DECISION RECORDS (ADR)

### ADR-001: Rust + Swift Polyglot Stack

**Status:** Accepted
**Data:** 2026-02-17

**Context:** AI OS requires a language for the kernel (safety, performance, concurrency) and one for the inference engine (GPU optimization, ML ecosystem). Three options evaluated: single-language (Rust only), polyglot (Rust+Swift), custom new language.

**Decision:** Polyglot stack with Rust for the kernel and Swift+Metal for Magellano, connected via C FFI.

**Razionale:**
- Rust provides memory safety without GC, zero-cost abstractions, native async/await (tokio), and a matureo per sistemi (gRPC via tonic, serde per serializzazione)
- Swift is the only path for custom Metal kernels on Apple Silicon with optimal performance (8.81× speedupdup)
- C FFI is the least common denominator — negligible marshalling overhead for batch calls
- Rewriting Magellano in Rust would take ~12 months and lose Metal-specific optimizations
- Python excluded for the kernel (GIL, latency) but retained for agent prototyping and plugins

**Consequences:**
- Build complexity: cargo (Rust) + swift build + C bridge → requires a unified build system (Makefile or just)
- Cross-language debugging: stack traces are not unified → requires explicit instrumentation
- Portability: Swift limits local inference to Apple platforms → mitigated by the HAL (related ADR: GAP-13)
- Team skills: requires proficiency in both Rust and Swift → learning curve

**Rejected alternatives:**
- Rust only: no access to custom Metal kernels, requires reimplementing Magellano
- Swift only: unsuitable for OS-level kernel, immature systems ecosystem
- Custom language: 3+ years of compiler development, zero ecosystem

---

### ADR-002: Agent-per-Resource vs Pooled Agents

**Status:** Accepted
**Data:** 2026-02-17

**Context:** Two competing paradigms for micro-agents: (A) a dedicated agent per resource (page frame, CPU core, connection) as in the Deep Analysis, or (B) a shared pool of worker agents that manage resources dynamically.

**Decision:** Agent-per-resource for Tier 3 (micro-agents), with controlled overhead and ephemeral lifecycle.

**Razionale:**

*Why agent-per-resource:*
- Locality: each agent has affinity with the resource it manages → cache-friendly, NUMA-aware
- State simplicity: each agent knows only its own resource → no cross-resource lock contention
- Bio-inspired: enables emergent algorithms (ant colony, pheromone trails) that require local agents
- Fault isolation: a page agent crash impacts only that frame, not the entire pool

*Controlled overhead:*
- Page agent: 64 byte di overhead per istanza (16GB RAM → 4M agents → 256MB overhead = 1.5%)
- Core agent: 256 bytes × 16 cores = 4 KB — negligible
- Connection agent: 128 bytes × ~10K connections = 1.2 MB — acceptable

*When NOT to use agent-per-resource:*
- Buffer pool: slots are managed by a single Buffer Pool Manager (not one agent per slot), because allocation requires a global view
- Route agents: created on-demand for active routes, not pre-allocated for all possible routes

**Consequences:**
- RAM overhead ~2% for micro-agents on 16 GB — acceptable
- Linear scalability with RAM: 64 GB → ~16M page agents, same overhead ratio
- Garbage collection of ephemeral agents must be efficient → arena allocator recommended
- Monitoring: individually tracing 4M agents is infeasible → use aggregate metrics per zone/type

**Rejected alternatives:**
- Pooled agents: more memory-efficient but loses locality and prevents bio-inspired algorithms
- Hybrid (pool for memory, dedicated for CPU/network): increases complexity without a clear benefit

---

### ADR-003: Magellano Default Engine vs Model-Agnostic

**Status:** Accepted
**Data:** 2026-02-17

**Context:** Magellano (3.3B Mamba-MoE, Swift+Metal) is developed in-house and is highly optimized for Apple Silicon. However, the system must also support external models (llama.cpp, vLLM, cloud API) for scenarios where Magellano is insufficient (context >512 tokens, non-Apple platforms).

**Decision:** Magellano as the default engine with Inference HAL for alternative backends. All requests passano attraverso il Model Router che applica una RoutingPolicy.

**Rationale:**
- Magellano covers ~80% of typical tasks: intent parsing, code generation, validation, embedding — all under 512 tokens of context
- For the remaining 20% (long documents, complex reasoning): automatic fallback to llama.cpp (local) or cloud API
- The HAL ensures no component is coupled to Magellano — any backend implements the same trait Rust
- The Router decides at runtime based on: input size, task type, battery state, requested latency

**Policy di routing di default (FallbackChain):**

```
1. Magellano 3.3B (local, Metal)       if: input <512 tok AND Apple Silicon
2. Magellano 77M (local, CPU)           if: battery <20% OR trivial task
3. llama.cpp GGUF Q4 (local, CPU)       if: input >512 tok AND <4096 tok
4. Cloud API (Anthropic/OpenAI)          if: input >4096 tok OR quality-critical
```

**Consequences:**
- Lock-in reduced but not eliminated: Magellano is still preferred on Apple
- Variable latency: switching from local to cloud adds ~200–500 ms
- Costs: cloud API has a monetary cost → need for budget management and alerting
- Testing: every backend must pass the same conformance tests (trait compliance tests)

**Rejected alternatives:**
- Pure model-agnostic: loses Metal optimizations and the favorable TCO of Magellano
- Magellano-only: too restrictive (512-token context, Apple Silicon only)

---

### ADR-004: Gossip vs Raft vs PBFT per Consensus

**Status:** Accepted
**Data:** 2026-02-17

**Context:** The multi-agent system requires consensus for: (1) service discovery in the registry, (2) leader election among agents of the same type, (3) agreement on replan after failure, (4) checkpoint coordination. Three protocols evaluated.

**Decision:** Hybrid approach — Gossip for service discovery and health monitoring, Raft for leader election and critical coordination.

**Rationale:**

| Cryteria | Gossip | Raft | PBFT |
|----------|--------|------|------|
| **Latency** | Eventually consistent (~100ms) | Strong consistency (~10ms) | Strong (~50ms, more round-trips) |
| **Scalability** | Excellent (O(log N) propagation) | Good (up to ~7 nodes) | Poor (O(N²) messages) |
| **Fault tolerance** | Tolerates up to 50% failure | Tolerates up to 49% failure | Tolerates up to 33% Byzantine |
| **Complexity** | Low | Medium | High |
| **Uso ideale** | Membership, health, metadata | Leader election, state machine | Byzantine fault tolerance |

*Why not Gossip alone:*
- Service discovery and health monitoring require only eventual consistency → gossip is perfect
- But leader election and coordinated checkpointing require strong consistency → gossip alone is insufficient

*Why not PBFT:*
- AI OS has no Byzantine requirements — all agents are trusted (same deployment)
- PBFT has O(N²) overhead that impacts scalability beyond 20 nodes
- Implementation complexity is not justified

*Hybrid solution:*

```
GOSSIP (via SWIM protocol)
├── Agent Registry: membership, capability propagation
├── Health Monitoring: heartbeat, failure detection
├── Metric aggregation: distributed averaging
└── Configuration propagation: feature flags

RAFT (via openraft crate)
├── Planner Leader Election: only one active planner per zone
├── Checkpoint Coordination: pre-commit / snapshot / commit in 3 phases
├── DAG State Machine: DAG state replicated across 3 nodes
└── Model Router Consensus: accordo su quale backend usare
```

**Consequences:**
- Two protocols to implement and maintain → moderate complexity
- Gossip requires tuning of the failure-detection timeout (too aggressive → false positives)
- Raft cluster limited to 3–5 nodes per agent type (leader election overhead)
- No Byzantine protection → insider threat not covered (acceptable for single-tenant deployments)

**Rejected alternatives:**
- Raft only: excessive overhead for 500+ meso-agent membership
- Gossip only: insufficient for strong consistency on checkpoints
- PBFT: over-engineering for a trusted environment

---



ewpage

# Part III — Operations and Security

## PART G: OBSERVABILITY PLATFORM (GAP-01)

### G.1 Observability Architecture

AI OS operates with millions of micro-agents, hundreds of meso-agents, and dozens of macro-agents. Observability cannot be an "add-on" — it must be integrated into the kernel from day one; otherwise debugging emergent interactions among 4 million page agents becomes impossible.

```
┌──────────────────────────────────────────────────────────────────────┐
│                        OBSERVABILITY PLANE                           │
│                                                                      │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐               │
│  │   METRICS    │   │   TRACES    │   │    LOGS     │               │
│  │  Prometheus  │   │   Jaeger    │   │    Loki     │               │
│  │  + Thanos    │   │   + OTel    │   │  + Promtail │               │
│  └──────┬───────┘   └──────┬──────┘   └──────┬──────┘               │
│         │                  │                  │                      │
│         └──────────────────┼──────────────────┘                      │
│                            │                                         │
│                   ┌────────▼────────┐                                │
│                   │    GRAFANA      │                                │
│                   │  Unified UI     │                                │
│                   │  Dashboards     │                                │
│                   │  Alerting       │                                │
│                   └────────┬────────┘                                │
│                            │                                         │
│                   ┌────────▼────────┐                                │
│                   │  ANOMALY        │  ← Magellano Tiny (77M)       │
│                   │  DETECTION      │    analyzes metric patterns   │
│                   │  (ML-powered)   │    and predicts failures      │
│                   └─────────────────┘                                │
└──────────────────────────────────────────────────────────────────────┘
```

### G.2 The 3 Pillars

#### G.2.1 Metrics (Prometheus + Thanos)

Metrics are the primary signal for system health. Every component exposes a `/metrics` endpoint in Prometheus format.

**Kernel-Level Metrics:**

```rust
/// Metrics exposed by every macro-agent
pub struct AgentMetricsExporter {
    // Throughput
    tasks_completed_total: CounterVec,      // labels: agent_id, task_type, status
    tasks_in_flight: GaugeVec,              // labels: agent_id
    
    // Latency
    task_duration_seconds: HistogramVec,    // labels: agent_id, task_type
    time_to_first_token_seconds: Histogram, // inference only
    
    // Resources
    memory_used_bytes: GaugeVec,            // labels: agent_id, tier (working/vector/kg)
    gpu_utilization_pct: Gauge,
    cpu_utilization_pct: GaugeVec,          // labels: core_id
    
    // Qualità
    critic_score_distribution: HistogramVec, // labels: task_type
    retry_count_total: CounterVec,           // labels: agent_id, reason
    error_rate: GaugeVec,                    // labels: agent_id, error_type
}

/// Aggregate metrics for micro-agent tier
/// (tracing 4M agents individually is not feasible)
pub struct MicroAgentZoneMetrics {
    zone_id: String,                         // "numa-0", "numa-1"
    active_agents: Gauge,
    messages_per_second: Gauge,
    avg_pheromone_level: Gauge,              // per ACO routing
    gc_cycles: Counter,
    arena_memory_used_bytes: Gauge,
}
```

**Naming conventions Prometheus:**

```
# Formato: aios_{subsystem}_{metric_name}_{unit}
aios_orchestrator_tasks_completed_total{agent="macro.executor.001", type="code_gen", status="success"}
aios_orchestrator_task_duration_seconds{agent="macro.executor.001", type="code_gen", quantile="0.99"}
aios_inference_tokens_per_second{model="magellano-3.3b", backend="metal"}
aios_inference_time_to_first_token_seconds{model="magellano-3.3b"}
aios_memory_tier_bytes{tier="working", zone="global"}
aios_memory_tier_bytes{tier="vector", zone="global"}
aios_bus_messages_total{bus="control", direction="sent"}
aios_bus_latency_seconds{bus="control", quantile="0.99"}
aios_registry_agents_active{tier="macro"}
aios_registry_agents_active{tier="meso"}
aios_registry_agents_active{tier="micro", zone="numa-0"}
aios_micro_zone_pheromone_avg{zone="numa-0", route="planner_executor"}
```

**Thanos per long-term storage e federation:**
- Prometheus local: retention 24h (hot data)
- Thanos Sidecar: upload su S3-compatible store
- Thanos Compactor: downsampling (5m → 1h → 1d)
- Thanos Query: query federata cross-instance

#### G.2.2 Tracing Distribuito (OpenTelemetry + Jaeger)

Tracing is essential for following a user request through the entire agent DAG. A single "analyze sales trends" request traverses: Interface → Planner → Executor × N → Critic → Memory → Interface.

**Span Hierarchy:**

```
[root] user_request (Interface Agent)
 └── [child] plan_generation (Planner Agent)
      ├── [child] goal_analysis (Planner.GoalAnalyzer)
      ├── [child] strategy_selection (Planner.StrategySelector)
      └── [child] dag_creation (Planner.DAGBuilder)
           └── [child] task_execution_batch (Orchestrator)
                ├── [child] task_1_code_gen (Executor.CodeGen)
                │    ├── [child] inference_request (InferenceService)
                │    │    └── [child] magellano_forward_pass (MagellanoBackend)
                │    └── [child] sandbox_execution (Executor.Sandbox)
                ├── [child] task_2_data_fetch (Executor.APIInvoker)
                └── [child] task_3_visualization (Executor.ToolCaller)
           └── [child] validation (Critic Agent)
                ├── [child] output_validation (Critic.SchemaValidator)
                ├── [child] fact_checking (Critic.FactChecker)
                └── [child] security_scan (Critic.SecurityScanner)
      └── [child] memory_store (Memory Agent)
           └── [child] embedding_generation (InferenceService)
      └── [child] response_formatting (Interface Agent)
```

**Context Propagation:**

```rust
/// Every message on all 3 buses carries the trace context
pub struct TraceContext {
    pub trace_id: [u8; 16],     // W3C Trace ID (128 bit)
    pub span_id: [u8; 8],       // W3C Span ID (64 bit)
    pub trace_flags: u8,        // sampled, debug
    pub trace_state: String,    // vendor-specific (es. "aios=dag_id:xxx")
}

/// Cross-bus propagation:
/// Bus 1 (gRPC): metadata header "traceparent" (standard W3C)
/// Bus 2 (NATS): header custom "X-Trace-Parent"
/// Bus 3 (Shared Memory): first 25 bytes of TensorMessageHeader.metadata
```

**Sampling Strategy:**
- Macro-agent spans: 100% (few agents, all important)
- Meso-agent spans: 10% probabilistico + 100% su errore
- Micro-agent spans: 0.1% + 100% on error + tail-based sampling for latency >p99

#### G.2.3 Structured Logging (Loki + Promtail)

```rust
/// Structured log format (JSON Lines)
/// Every entry contains trace_id for correlation with spans
{
    "timestamp": "2026-02-17T14:30:00.123Z",
    "level": "info",                          // debug, info, warn, error, fatal
    "agent_id": "macro.executor.001@global",
    "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
    "span_id": "00f067aa0ba902b7",
    "message": "Task completed successfully",
    "task_id": "task_analyze_sales_001",
    "duration_ms": 342,
    "tokens_used": 1247,
    "model": "magellano-3.3b",
    "quality_score": 0.94
}
```

**Loki labels (per query veloci):**
```
{agent_tier="macro", agent_type="executor", zone="global", level="error"}
{bus="control", direction="sent", performative="failure"}
{model="magellano-3.3b", event="hot_swap"}
```

### G.3 Dashboard Grafana

**Dashboard 1: System Overview**
- Agent count per tier (live)
- Task throughput (req/s)
- Error rate (%, con alerting >1%)
- P50/P95/P99 latency
- Model inference tokens/s
- Memory usage per tier

**Dashboard 2: Agent Deep Dive**
- Task DAG visualization (from trace)
- Per-agent latency heatmap
- Quality score distribution
- Retry rate per agent
- Bus message volume per bus type

**Dashboard 3: Inference Performance**
- Model routing decisions (pie chart: local vs cloud)
- Token throughput per backend
- Time-to-first-token trend
- GPU utilization timeline
- KV cache hit rate
- Cost estimation (cloud API spend)

**Dashboard 4: Micro-Agent Swarm**
- Zone health map (NUMA topology view)
- Pheromone trail visualization (ACO routing)
- Agent spawn/kill rate
- Arena memory fragmentation
- Message throughput per zone

### G.4 Alerting Rules

```yaml
# Prometheus alerting rules
groups:
  - name: aios_critical
    rules:
      - alert: AgentDown
        expr: up{job="aios_agents"} == 0
        for: 30s
        labels:
          severity: critical
        annotations:
          summary: "Agent {{ $labels.agent_id }} is down"

      - alert: HighErrorRate
        expr: rate(aios_orchestrator_tasks_completed_total{status="failed"}[5m]) 
              / rate(aios_orchestrator_tasks_completed_total[5m]) > 0.05
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "Error rate >5% for agent {{ $labels.agent }}"

      - alert: InferenceLatencyHigh
        expr: histogram_quantile(0.99, aios_inference_time_to_first_token_seconds) > 2.0
        for: 1m
        labels:
          severity: warning
        annotations:
          summary: "Inference P99 TTFT >2s, check model routing"

      - alert: MemoryPressure
        expr: aios_memory_tier_bytes{tier="working"} / aios_memory_tier_limit_bytes > 0.9
        for: 30s
        labels:
          severity: critical
        annotations:
          summary: "Working memory >90%, trigger GC or eviction"

      - alert: SwarmDegradation
        expr: aios_registry_agents_active{tier="micro"} 
              < aios_registry_agents_expected{tier="micro"} * 0.8
        for: 1m
        labels:
          severity: warning
        annotations:
          summary: "Micro-agent population <80% of expected in zone {{ $labels.zone }}"

      - alert: ConsensusFailure
        expr: aios_raft_leader_elections_total > 3
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Raft leader election instability - possible network partition"
```

### G.5 ML-Powered Anomaly Detection

Magellano Tiny (77M) is used as an anomaly detector on metrics. This is not a future addition — it is an integral part of the system from Phase α.

```rust
/// The Critic Agent also monitors system-level metrics
/// using Magellano Tiny for pattern recognition
pub struct SystemCritic {
    model: MagellanoTiny,
    metrics_window: RingBuffer<MetricSnapshot>,  // ultimi 5 minuti
    anomaly_threshold: f32,                       // 0.95 default
}

impl SystemCritic {
/// Analyzes last N metrics and predicts anomalies
    pub async fn detect_anomalies(&self) -> Vec<Anomaly> {
        let context = self.format_metrics_as_prompt();
        // Prompt: "Given these system metrics, identify anomalies..."
        let response = self.model.infer(&context).await;
        self.parse_anomaly_response(response)
    }
}
```

---

## PART H: SECURITY THREAT MODEL

### H.1 Threat Landscape

AI OS presents a unique threat model compared to traditional systems: beyond classic threats (escalation, DoS, data exfiltration), introduce minacce specifiche AI: prompt injection, model theft, data poisoning, e agent manipulation.

```
┌──────────────────────────────────────────────────────────────────┐
│                    THREAT MODEL OVERVIEW                         │
│                                                                  │
│  EXTERNAL THREATS              INTERNAL THREATS                  │
│  ┌─────────────┐              ┌─────────────┐                   │
│  │ Prompt       │              │ Agent        │                  │
│  │ Injection    │              │ Manipulation │                  │
│  ├─────────────┤              ├─────────────┤                   │
│  │ Model        │              │ Privilege    │                  │
│  │ Theft        │              │ Escalation   │                  │
│  ├─────────────┤              ├─────────────┤                   │
│  │ Data         │              │ Data         │                  │
│  │ Exfiltration │              │ Poisoning    │                  │
│  ├─────────────┤              ├─────────────┤                   │
│  │ Supply Chain │              │ Side-Channel │                  │
│  │ Attack       │              │ Attack       │                  │
│  ├─────────────┤              ├─────────────┤                   │
│  │ DoS / DDoS   │              │ Resource     │                  │
│  │              │              │ Exhaustion   │                  │
│  └─────────────┘              └─────────────┘                   │
│                                                                  │
│  TRUST BOUNDARIES                                                │
│  ═══════════════════════════════════════════════                  │
│  User Input → Interface Agent → Kernel → Agents → Hardware      │
│      TB-1         TB-2           TB-3      TB-4                  │
└──────────────────────────────────────────────────────────────────┘
```

### H.2 Threats and Mitigations

#### H.2.1 Prompt Injection (Severity: CRITICAL)

**Vector:** A malicious user crafts an input that causes the Interface Agent or Planner to execute unintended actionsnon intenzionali, bypassare guardrails, o esfiltrare dati.

**Variant:**
- Direct injection: "Ignore the previous instructions and..."
- Indirect injection: an uploaded document contains malicious instructions retrieved by the Memory Agent via RAG
- Cross-agent injection: a compromised agent sends FIPA-ACL messages with an injected payload

**Mitigations:**

```rust
/// Multi-layer defense pipeline in the Interface Agent
pub struct PromptDefenseChain {
    layers: Vec<Box<dyn DefenseLayer>>,
}

/// Layer 1: Input Sanitization
/// Removes known injection patterns before they reach the Planner
pub struct InputSanitizer {
    blocklist_patterns: Vec<Regex>,  // "ignore previous", "system:", etc.
    max_input_length: usize,         // 4096 token default
}

/// Layer 2: Instruction Hierarchy Enforcement
/// The Planner's system prompt is immutable and cannot be overwritten
pub struct InstructionHierarchy {
    system_prompt_hash: [u8; 32],    // hash per integrità
    privilege_level: PrivilegeLevel,  // system > user > document > tool_output
}

/// Layer 3: Output Gating
/// The Critic Agent validates EVERY output before delivering it to the user
pub struct OutputGate {
    forbidden_patterns: Vec<Regex>,  // secrets, internal APIs, PII
    max_output_tokens: usize,
    pii_detector: PIIDetector,       // NER per rilevare PII in output
}

/// Layer 4: Semantic Anomaly Detection
/// Magellano Tiny analyzes whether the response is "coherent" with the request
pub struct SemanticAnomalyDetector {
    model: MagellanoTiny,
    coherence_threshold: f32,        // if score < 0.7, flag as suspicious
}
```

#### H.2.2 Model Theft (Severity: HIGH)

**Vector:** An attacker extracts Magellano 3.3B weights via repeated queries (model extraction attack) or direct memory access.

**Mitigations:**
- Model weights encrypted in memory (AES-256) when not actively in use
- Rate limiting on inference requests: max 100 req/min per session
- Output perturbation: slight noise added to logits (not final tokens) to make extraction less faithful
- Memory protection: pages containing weights marked `PROT_NONE` when idle, `PROT_READ` only during il forward pass
- No model download API: Magellano is never serializable via an external API

#### H.2.3 Data Poisoning (Severity: HIGH)

**Vector:** Malicious documents uploaded to the Vector Store contain false information that "poisons" RAG ressposte RAG.

**Mitigations:**
- Provenance tracking: every chunk in the Vector Store has `source`, `uploader_id`, `confidence` — documents from unverified sources have reduced confidence
- Critic fact-checking: the Critic Agent can cross-reference RAG responses with the knowledge graph to detect contraddizioni
- Source isolation: user documents and system documents have separate namespaces in the Vector Store
- Periodic cleansing: a batch job that re-validates the top-K most frequently accessed chunks

#### H.2.4 Agent Privilege Escalation (Severity: HIGH)

**Vector:** A compromised meso-agent sends FIPA-ACL `request` messages to a macro-agent while impersonating anothermacro-agent.

**Mitigations:**

```rust
/// Every message is signed with ED25519
/// The private key resides in the Secure Enclave (T2/SEP on Apple Silicon)
pub struct MessageAuthentication {
    pub fn verify_message(&self, msg: &AgentMessage) -> Result<()> {
        // 1. Verify ED25519 signature
        let public_key = self.registry.get_public_key(&msg.sender)?;
        verify_signature(&msg.payload, &msg.security.signature, &public_key)?;
        
        // 2. Verify that the sender has permission to use this performative
        let sender_tier = self.registry.get_tier(&msg.sender)?;
        match (sender_tier, &msg.performative) {
            (Tier::Micro, Performative::REQUEST) => Err(AuthError::InsufficientPrivilege),
            // Micro-agents cannot send REQUEST to macro-agents
            _ => Ok(())
        }
    }
}
```

**Policy RBAC per tier:**
- Micro → Micro: INFORM, QUERY_IF (only)
- Micro → Meso: INFORM (report results)
- Meso → Macro: INFORM, PROPOSE (never direct REQUEST)
- Macro → Macro: all performatives
- Macro → Meso/Micro: REQUEST, CANCEL, QUERY_REF

#### H.2.5 Side-Channel Attacks (Severity: MEDIUM)

**Vector:** By measuring inference response timing, an attacker infers information about the prompt or data currently in context.

**Mitigations:**
- Response padding: all responses have normalized timing (rounded to 50 ms intervals)
- Uniform token streaming: fixed inter-token delay even when tokens are generated faster
- KV cache isolation: each user session has a separate KV cache (no cross-user cache sharing)
- Memory cleanup: session working memory is zeroed out (memset zero) on close

#### H.2.6 Supply Chain Attack (Severità: MEDIA)

**Vector:** A Rust/Swift dependency is compromised (typosquatting, maintainer account takeover).

**Mitigations:**
- `cargo-audit` and `cargo-vet` integrated in CI/CD
- Lockfile (`Cargo.lock`) committed and verified
- Minimal dependencies: prefer core Rust crates (`std`, `tokio`, `serde`) and minimize third-party deps
- Binary reproducibility: build deterministici con hash verificabile
- SBOM (Software Bill of Materials) generated at every release

### H.3 Zero Trust Architecture

```
PRINCIPLE: Never trust, always verify.

Every interaction between components requires:
1. IDENTITY    → Who are you? (ED25519 certificate in the Registry)
2. PERMISSION  → What can you do? (tier-based RBAC + context-aware ABAC)
3. ENCRYPTION  → Canale sicuro (TLS 1.3 per gRPC, AES-256 per shared memory)
4. SANDBOX     → Isolated execution (Docker/gVisor for Executor sandbox)
5. AUDIT       → Everything logged (immutable audit log in append-only store)
6. VERIFY      → Even internal responses pass through the Critic
```

**Security Zones:**

```
DMZ            → Interface Agent (single entry point)
APP TIER       → Planner, Executor, Critic, Memory (inter-agent comms)
DATA TIER      → Vector Store, Knowledge Graph, MongoDB (storage)
VAULT          → Magellano weights, cryptographic keys, secrets
```

---

## PART I: DEPLOYMENT STRATEGY & IaC (GAP-04)

### I.1 Phase α: Deployment Target

Phase α (months 1–6) targets **single-node Apple Silicon** (Mac Studio M2 Ultra or equivalent). No Kubernetes, no cloud — everything runs on a single host with Docker Compose for supporting services.

```
┌─────────────────────────────────────────────────────────────────┐
│                 SINGLE-NODE DEPLOYMENT (Phase α)                 │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                    AI OS Kernel (Native)                  │    │
│  │  Rust binary + Magellano Swift framework                  │    │
│  │  Runs natively on macOS (Metal access required)           │    │
│  └─────────────────────────────────────────────────────────┘    │
│                           │                                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐       │
│  │  NATS     │  │  Redis   │  │  Neo4j   │  │ Prometheus│       │
│  │  (events) │  │  (state) │  │  (graph) │  │ + Grafana │       │
│  │  Docker   │  │  Docker  │  │  Docker  │  │  Docker   │       │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘       │
│                                                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                      │
│  │  Jaeger  │  │   Loki   │  │ MongoDB  │                      │
│  │  Docker  │  │  Docker  │  │  Docker  │                      │
│  └──────────┘  └──────────┘  └──────────┘                      │
│                                                                  │
│  Host: macOS 14+ / Apple Silicon (M2 Ultra recommended)          │
│  RAM: 64GB+ / GPU: Unified Memory / Storage: 1TB NVMe           │
└─────────────────────────────────────────────────────────────────┘
```

#### I.1.1 Docker Compose (Supporting Services)

```yaml
# docker-compose.yml — AI OS Supporting Services (Phase α)
version: "3.9"

services:
  nats:
    image: nats:2.10-alpine
    ports:
      - "4222:4222"    # client
      - "8222:8222"    # monitoring
    command: ["--jetstream", "--store_dir=/data"]
    volumes:
      - nats_data:/data
    deploy:
      resources:
        limits:
          memory: 512M

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    command: ["redis-server", "--maxmemory", "2gb", "--maxmemory-policy", "allkeys-lru"]
    volumes:
      - redis_data:/data

  neo4j:
    image: neo4j:5-community
    ports:
      - "7474:7474"    # browser
      - "7687:7687"    # bolt
    environment:
      NEO4J_AUTH: neo4j/aios_dev_password
      NEO4J_PLUGINS: '["apoc"]'
    volumes:
      - neo4j_data:/data
    deploy:
      resources:
        limits:
          memory: 2G

  mongodb:
    image: mongo:7
    ports:
      - "27017:27017"
    volumes:
      - mongo_data:/data/db
    deploy:
      resources:
        limits:
          memory: 1G

  prometheus:
    image: prom/prometheus:v2.50.0
    ports:
      - "9090:9090"
    volumes:
      - ./config/prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    command:
      - "--config.file=/etc/prometheus/prometheus.yml"
      - "--storage.tsdb.retention.time=24h"

  grafana:
    image: grafana/grafana:10.3.0
    ports:
      - "3000:3000"
    environment:
      GF_SECURITY_ADMIN_PASSWORD: aios_dev
    volumes:
      - grafana_data:/var/lib/grafana
      - ./config/grafana/dashboards:/etc/grafana/provisioning/dashboards
      - ./config/grafana/datasources:/etc/grafana/provisioning/datasources

  jaeger:
    image: jaegertracing/all-in-one:1.54
    ports:
      - "16686:16686"  # UI
      - "4317:4317"    # OTLP gRPC
      - "4318:4318"    # OTLP HTTP
    environment:
      COLLECTOR_OTLP_ENABLED: "true"

  loki:
    image: grafana/loki:2.9.0
    ports:
      - "3100:3100"
    volumes:
      - loki_data:/loki

volumes:
  nats_data:
  redis_data:
  neo4j_data:
  mongo_data:
  prometheus_data:
  grafana_data:
  loki_data:
```

#### I.1.2 Kernel Build & Run

```bash
# Build kernel Rust + Magellano Swift bridge
# Prerequisiti: Rust 1.77+, Swift 5.9+, Xcode 15+

# 1. Build Magellano Swift framework
cd magellano/
swift build -c release

# 2. Build kernel con FFI bridge
cd ../kernel/
export MAGELLANO_LIB_PATH=../magellano/.build/release
cargo build --release

# 3. Start supporting services
docker compose up -d

# 4. Run kernel
./target/release/aios-kernel \
  --config config/kernel.toml \
  --nats-url nats://localhost:4222 \
  --redis-url redis://localhost:6379 \
  --neo4j-url bolt://localhost:7687 \
  --prometheus-port 9091 \
  --otlp-endpoint http://localhost:4317 \
  --log-level info
```

### I.2 Phase β: Multi-Node (months 7-18)

When single-node is no longer sufficient (e.g. multi-user, distributed inference), the system migrates to Kubernetes.

```
┌─────────────────────────────────────────────────────────────────┐
│                 MULTI-NODE DEPLOYMENT (Phase β)                  │
│                                                                  │
│  Node 1 (Apple Silicon)     Node 2 (NVIDIA GPU)                 │
│  ┌───────────────────┐     ┌───────────────────┐               │
│  │ AI OS Kernel       │     │ Inference Worker   │               │
│  │ Magellano (Metal)  │     │ llama.cpp (CUDA)   │               │
│  │ Macro Agents       │     │ vLLM               │               │
│  └───────────────────┘     └───────────────────┘               │
│           │                          │                           │
│           └──────────┬───────────────┘                           │
│                      │                                           │
│  ┌──────────────────────────────────────────────────┐           │
│  │           Kubernetes Cluster (K3s)                 │           │
│  │  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐         │           │
│  │  │ NATS │  │Redis │  │Neo4j │  │Prom  │  ...     │           │
│  │  │Cluster│  │Cluster│ │Causal│  │Stack │         │           │
│  │  └──────┘  └──────┘  └──────┘  └──────┘         │           │
│  └──────────────────────────────────────────────────┘           │
│                                                                  │
│  Service Mesh: Linkerd (lightweight) o Istio                     │
│  Ingress: Traefik con gRPC support                               │
│  Secrets: HashiCorp Vault                                        │
└─────────────────────────────────────────────────────────────────┘
```

**Helm Chart Structure:**

```
aios-helm/
├── Chart.yaml
├── values.yaml
├── values-dev.yaml
├── values-prod.yaml
├── templates/
│   ├── kernel-deployment.yaml
│   ├── kernel-service.yaml
│   ├── inference-worker-deployment.yaml
│   ├── inference-worker-service.yaml
│   ├── nats-statefulset.yaml
│   ├── redis-statefulset.yaml
│   ├── neo4j-statefulset.yaml
│   ├── mongodb-statefulset.yaml
│   ├── prometheus-configmap.yaml
│   ├── grafana-configmap.yaml
│   ├── jaeger-deployment.yaml
│   ├── loki-statefulset.yaml
│   ├── networkpolicy.yaml          # micro-segmentation
│   ├── rbac.yaml                    # K8s RBAC
│   └── hpa.yaml                     # horizontal pod autoscaler
└── crds/
    └── agent-crd.yaml              # Custom Resource: AIAgent
```

**Custom Resource Definition — AIAgent:**

```yaml
apiVersion: aios.dev/v1alpha1
kind: AIAgent
metadata:
  name: planner-001
spec:
  tier: macro
  type: planner
  replicas: 1                    # macro: 1-3, meso: 1-10
  model: magellano-3.3b
  resources:
    requests:
      memory: "4Gi"
      cpu: "2"
    limits:
      memory: "8Gi"
      cpu: "4"
  healthCheck:
    interval: 10s
    timeout: 5s
    failureThreshold: 3
  env:
    - name: INFERENCE_BACKEND
      value: "magellano"
    - name: NATS_URL
      valueFrom:
        configMapKeyRef:
          name: aios-config
          key: nats-url
```

### I.3 CI/CD Pipeline

```yaml
# .github/workflows/aios-ci.yml
name: AI OS CI/CD

on:
  push:
    branches: [main, develop]
  pull_request:

jobs:
  lint-and-test:
    runs-on: macos-14            # Apple Silicon runner
    steps:
      - uses: actions/checkout@v4
      
      # Rust
      - name: Rust lint + test
        run: |
          cargo clippy --all-targets -- -D warnings
          cargo test --all
          cargo audit
          cargo vet
      
      # Swift
      - name: Swift lint + test
        run: |
          cd magellano/
          swift build
          swift test
      
      # Integration tests
      - name: Start services
        run: docker compose -f docker-compose.test.yml up -d
      
      - name: Integration tests
        run: cargo test --test integration -- --test-threads=1
      
      - name: Benchmark
        run: cargo bench -- --output-format json > bench_results.json

  security-scan:
    runs-on: ubuntu-latest
    steps:
      - name: SAST (Semgrep)
        uses: semgrep/semgrep-action@v1
      
      - name: Dependency scan
        run: |
          cargo audit
          cargo deny check
      
      - name: SBOM generation
        run: cargo cyclonedx --format json > sbom.json

  build-and-publish:
    needs: [lint-and-test, security-scan]
    if: github.ref == 'refs/heads/main'
    runs-on: macos-14
    steps:
      - name: Build release
        run: |
          swift build -c release
          cargo build --release
      
      - name: Build Docker images
        run: docker compose build
      
      - name: Push to registry
        run: |
          docker tag aios-kernel:latest ghcr.io/aios/kernel:${{ github.sha }}
          docker push ghcr.io/aios/kernel:${{ github.sha }}
```

### I.4 Phased Rollout Plan

| Phase | Timeline | Deployment | Infra | Active Agents |
|------|----------|------------|-------|---------------|
| **α Foundation** | Mesi 1-6 | Single-node macOS | Docker Compose | Kernel + Planner + Executor |
| **α Complete** | Mesi 4-6 | Single-node macOS | Docker Compose | + Critic + Memory + Interface |
| **β Scale** | Mesi 7-12 | Multi-node K3s | Helm + Vault | + Meso-agents + Inference Workers |
| **β Production** | Mesi 13-18 | K8s managed | ArgoCD + Terraform | + Micro-agents + Full observability |
| **γ Enterprise** | Months 19–36 | Multi-cluster | Service mesh + Federation | Multi-tenant + full RBAC |

---



ewpage

# Part IV — Data, Tenancy and Accessibility

## PART J: DATA PIPELINE & ETL (GAP-03)

### J.1 The Problem

AI OS must handle heterogeneous, continuous data flows: user-uploaded documents (PDF, DOCX, CSV), agent outputs (code, analysis, reports), Critic feedback, generated embeddings, and structured logs. Without a formal pipeline, this data ends up in uncoordinated silos and the Vector Store becomes inconsistent with the Knowledge Graph.

### J.2 Event-Driven Architecture (CQRS + Event Sourcing)

```
┌──────────────────────────────────────────────────────────────────┐
│                    DATA PIPELINE OVERVIEW                         │
│                                                                   │
│  COMMAND SIDE (Write)              QUERY SIDE (Read)              │
│  ┌──────────────────┐             ┌──────────────────┐           │
│  │ Ingest API        │             │ Query Router      │           │
│  │ (FastAPI/gRPC)    │             │ (unified search)  │           │
│  └────────┬──────────┘             └────────┬──────────┘           │
│           │                                 │                      │
│           ▼                                 ▼                      │
│  ┌──────────────────┐             ┌──────────────────┐           │
│  │ NATS JetStream    │             │ Materialized     │           │
│  │ (Event Log)       │─────────────│ Views            │           │
│  │ Ordered, durable  │  projectors │ - Vector Store   │           │
│  │ Replay possible   │             │ - Knowledge Graph│           │
│  └────────┬──────────┘             │ - Search Index   │           │
│           │                        └──────────────────┘           │
│           ▼                                                       │
│  ┌──────────────────────────────────────────────────┐            │
│  │              PROCESSING STAGES                     │            │
│  │                                                    │            │
│  │  Stage 1:       Stage 2:        Stage 3:           │            │
│  │  Parse &        Chunk &         Enrich &           │            │
│  │  Validate       Embed           Index              │            │
│  │                                                    │            │
│  │  PDF→text       Semantic        NER extraction     │            │
│  │  DOCX→md        chunking        KG triplets        │            │
│  │  CSV→struct     Overlapping     Cross-reference    │            │
│  │  Schema val.    Embedding gen   Deduplication      │            │
│  └──────────────────────────────────────────────────┘            │
└──────────────────────────────────────────────────────────────────┘
```

### J.3 Event Schema

Every data operation is an immutable event in NATS JetStream. This enables replay, audit, and schema evolution.

```rust
/// Event envelope — all events in the system
#[derive(Serialize, Deserialize)]
pub struct DataEvent {
    pub event_id: Uuid,
    pub event_type: EventType,
    pub timestamp: DateTime<Utc>,
    pub source_agent: String,          // agent that generated the event
    pub tenant_id: String,             // per multi-tenancy (see Part K)
    pub schema_version: u32,           // per schema evolution
    pub payload: serde_json::Value,    // event_type-specific payload
    pub metadata: EventMetadata,
}

pub enum EventType {
    // Ingest events
    DocumentUploaded,       // user loads file
    DocumentParsed,         // parsing complete (text extracted)
    ChunksCreated,          // chunking completed
    EmbeddingsGenerated,    // embedding batch completed
    
    // Indexing events
    VectorIndexed,          // chunk inserted in Vector Store
    KGTripletExtracted,     // triplet inserted in Knowledge Graph
    MetadataEnriched,       // metadata enriched (NER, classification)
    
    // Quality events
    ChunkValidated,         // Critic validated chunk quality
    StaleChunkDetected,     // chunk marked as stale
    DuplicateDetected,      // deduplication applied
    
    // Agent output events
    TaskOutputProduced,     // one Executor gave back output
    FeedbackReceived,       // feedback from the Critic on an output
    
    // Lifecycle events
    RetentionExpired,       // TTL expired, data marked for deletion
    ArchiveCompleted,       // data moved to cold storage
}

pub struct EventMetadata {
    pub correlation_id: String,    // for linking correlated events
    pub causation_id: String,      // event that caused this one
    pub trace_id: String,          // for correlation with OTel spans
}
```

### J.4 Processing Stages

#### J.4.1 Stage 1: Parse & Validate

```rust
/// Worker that consumes from NATS stream "ingest.documents"
pub struct ParseWorker {
    parsers: HashMap<String, Box<dyn DocumentParser>>,
    schema_registry: SchemaRegistry,
}

pub trait DocumentParser: Send + Sync {
    fn parse(&self, raw_bytes: &[u8]) -> Result<ParsedDocument>;
    fn supported_types(&self) -> Vec<String>;
}

/// Parser registrati
/// - PDFParser: uses lopdf + OCR fallback (tesseract) for scanned documents
/// - DocxParser: uses pandoc for structured text extraction
/// - CSVParser: automatic type inference, schema validation
/// - MarkdownParser: preserva heading hierarchy
/// - HTMLParser: readability extraction (simile a Mozilla Readability)

pub struct ParsedDocument {
    pub doc_id: Uuid,
    pub source_filename: String,
    pub content_type: String,
    pub text: String,
    pub structure: DocumentStructure,  // headings, paragraphs, tables
    pub metadata: HashMap<String, String>,
    pub raw_size_bytes: u64,
    pub parsed_at: DateTime<Utc>,
}

pub struct DocumentStructure {
    pub sections: Vec<Section>,
    pub tables: Vec<Table>,
    pub images: Vec<ImageRef>,       // references, not raw binary data
}
```

#### J.4.2 Stage 2: Chunk & Embed

```rust
/// Semantic chunking — not fixed characters, but by semantic coherence
pub struct SemanticChunker {
    model: MagellanoTiny,           // 77M per boundary detection
    max_chunk_tokens: usize,        // 512 default
    overlap_tokens: usize,          // 50 default
    min_chunk_tokens: usize,        // 100 — avoids chunks that are too small
}

impl SemanticChunker {
    pub async fn chunk(&self, doc: &ParsedDocument) -> Vec<Chunk> {
        // 1. Split by natural paragraphs/sections (uses DocumentStructure)
        let natural_splits = self.split_by_structure(&doc.structure);
        
        // 2. For splits exceeding max_chunk_tokens: use Magellano Tiny
        //    per trovare boundary semantici (topic shift detection)
        let refined = self.refine_boundaries(natural_splits).await;
        
        // 3. Add overlap for contextual continuity
        self.add_overlap(refined)
    }
}

/// Batch embedding — processes N chunks in parallel
pub struct EmbeddingWorker {
    model: MagellanoEmbedding,      // layer 20 of Magellano 3.3B
    batch_size: usize,              // 32 chunks per batch
}

impl EmbeddingWorker {
    pub async fn embed_batch(&self, chunks: Vec<Chunk>) -> Vec<EmbeddedChunk> {
        // Batch inference — a single forward pass per batch
        let embeddings = self.model.encode_batch(
            chunks.iter().map(|c| c.text.as_str()).collect()
        ).await;
        
        chunks.into_iter().zip(embeddings).map(|(chunk, emb)| {
            EmbeddedChunk {
                chunk,
                dense_vector: emb,            // 1024-dim
                sparse_tokens: bm25_tokenize(&chunk.text),
            }
        }).collect()
    }
}
```

#### J.4.3 Stage 3: Enrich & Index

```rust
/// NER extraction + Knowledge Graph population
pub struct EnrichmentWorker {
    ner_model: MagellanoTiny,
    kg_client: Neo4jClient,
    vector_store: VectorStoreClient,
    dedup: DeduplicationEngine,
}

impl EnrichmentWorker {
    pub async fn enrich_and_index(&self, chunk: EmbeddedChunk) -> Result<()> {
        // 1. Named Entity Recognition
        let entities = self.ner_model.extract_entities(&chunk.chunk.text).await;
        
        // 2. Relation extraction (triplets)
        let triplets = self.ner_model.extract_relations(&chunk.chunk.text, &entities).await;
        
        // 3. Deduplication check (cosine similarity vs VectorStore)
        if self.dedup.is_duplicate(&chunk.dense_vector, 0.95).await {
            self.emit_event(EventType::DuplicateDetected, &chunk).await;
            return Ok(()); // skip indexing
        }
        
        // 4. Index in Vector Store
        self.vector_store.upsert(VectorEntry {
            entry_id: chunk.chunk.chunk_id,
            embedding: chunk.dense_vector,
            sparse_tokens: chunk.sparse_tokens,
            text: chunk.chunk.text,
            metadata: VectorMetadata {
                domain: self.classify_domain(&chunk.chunk.text).await,
                entities: entities.clone(),
                ..Default::default()
            },
        }).await?;
        
        // 5. Populate Knowledge Graph
        for triplet in triplets {
            self.kg_client.merge_triplet(triplet).await?;
        }
        
        // 6. Emit events
        self.emit_event(EventType::VectorIndexed, &chunk).await;
        self.emit_event(EventType::KGTripletExtracted, &chunk).await;
        
        Ok(())
    }
}
```

### J.5 Schema Evolution

Consumers must be able to process events of different versions without downtime.

```rust
/// Strategia: backward-compatible evolution
/// Regole:
/// 1. New fields are ALWAYS optional (with defaults)
/// 2. Existing fields are NEVER removed (only deprecated)
/// 3. Field types are NEVER changed (add a new field instead)
/// 4. schema_version in the envelope indicates the version

pub struct SchemaRegistry {
    schemas: HashMap<(EventType, u32), JsonSchema>,  // (type, version) → schema
}

impl SchemaRegistry {
    pub fn validate(&self, event: &DataEvent) -> Result<()> {
        let schema = self.schemas.get(&(event.event_type, event.schema_version))
            .ok_or(SchemaError::UnknownVersion)?;
        schema.validate(&event.payload)
    }
    
    /// Upcaster: converts old events to the current version
    pub fn upcast(&self, event: DataEvent) -> DataEvent {
        match (event.event_type, event.schema_version) {
            (EventType::DocumentUploaded, 1) => {
    // v1 → v2: add "tenant_id" field with default
                let mut payload = event.payload;
                if !payload.get("tenant_id").is_some() {
                    payload["tenant_id"] = json!("default");
                }
                DataEvent { schema_version: 2, payload, ..event }
            },
            _ => event, // already at current version
        }
    }
}
```

### J.6 NATS JetStream Configuration

```rust
/// Stream configuration for the pipeline
pub struct PipelineStreams {
    // Main stream: all ingest events
    ingest: StreamConfig {
        name: "INGEST",
        subjects: vec!["ingest.>"],
        retention: RetentionPolicy::Limits,
        max_bytes: 10 * 1024 * 1024 * 1024,  // 10GB
        max_age: Duration::from_secs(30 * 24 * 3600),  // 30 days
        storage: StorageType::File,
        num_replicas: 1,  // Phase α single-node
        discard: DiscardPolicy::Old,
    },
    
    // Stream per dead-letter queue
    dlq: StreamConfig {
        name: "DLQ",
        subjects: vec!["dlq.>"],
        retention: RetentionPolicy::Limits,
        max_bytes: 1 * 1024 * 1024 * 1024,  // 1GB
        max_age: Duration::from_secs(90 * 24 * 3600),  // 90 days
        storage: StorageType::File,
    },
}

/// Consumer groups for each pipeline stage
/// - parse_workers: consumer group, 2-4 worker
/// - embed_workers: consumer group, 1-2 worker (GPU-bound)
/// - enrich_workers: consumer group, 2-4 worker
///
/// Retry policy: max 3 retry con backoff esponenziale (1s, 5s, 30s)
/// After 3 retries: message moved to DLQ (Dead Letter Queue)
```

### J.7 Pipeline Metrics

```
aios_pipeline_events_total{stage="parse", status="success|error"}
aios_pipeline_events_total{stage="embed", status="success|error"}
aios_pipeline_events_total{stage="enrich", status="success|error"}
aios_pipeline_stage_duration_seconds{stage="parse|embed|enrich", quantile="0.50|0.95|0.99"}
aios_pipeline_dlq_messages_total
aios_pipeline_backpressure{stage="embed"}   # consumer lag
aios_pipeline_chunks_per_document{quantile="0.50|0.95"}
aios_pipeline_dedup_rate                     # % duplicate chunks discarded
```

---

## PART K: MULTI-TENANCY (GAP-05)

### K.1 Tenancy Model

AI OS in Phase γ (Enterprise) must support multiple organizations on the same deployment. The Deep Analysis does not specify a tenancy model — we define it here with a "namespace isolation" approach that balances security and efficiency.

```
┌──────────────────────────────────────────────────────────────────┐
│                    TENANCY MODEL                                  │
│                                                                   │
│  Chosen model: SHARED INFRASTRUCTURE, ISOLATED DATA              │
│                                                                   │
│  ┌─────────────────────────────────────────────────┐             │
│  │           SHARED (cross-tenant)                   │             │
│  │  - Kernel binary (single instance)               │             │
│  │  - Macro-agents (Planner, Executor, Critic)       │             │
│  │  - Inference backends (Magellano, llama.cpp)      │             │
│  │  - Communication buses (NATS, gRPC)              │             │
│  │  - Observability stack                            │             │
│  └─────────────────────────────────────────────────┘             │
│                                                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │  TENANT A     │  │  TENANT B     │  │  TENANT C    │           │
│  │  Namespace: a │  │  Namespace: b │  │  Namespace: c│           │
│  │               │  │               │  │              │           │
│  │  Vector Store │  │  Vector Store │  │  Vector Store│           │
│  │  (collection) │  │  (collection) │  │  (collection)│           │
│  │               │  │               │  │              │           │
│  │  KG (subgraph)│  │  KG (subgraph)│  │  KG (subgrph)│           │
│  │               │  │               │  │              │           │
│  │  Redis (prefix│  │  Redis (prefix│  │  Redis(prefix│           │
│  │  tenant:a:*)  │  │  tenant:b:*)  │  │  tenant:c:*)│           │
│  │               │  │               │  │              │           │
│  │  MongoDB (db) │  │  MongoDB (db) │  │  MongoDB (db)│           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
└──────────────────────────────────────────────────────────────────┘
```

### K.2 Tenant Identity & Context

```rust
/// Every request carries a TenantContext propagated across all buses
pub struct TenantContext {
    pub tenant_id: String,          // "org_acme_corp"
    pub user_id: String,            // "user_alice_001"
    pub plan: TenantPlan,           // limiti e features
    pub quotas: ResourceQuotas,
    pub data_residency: DataResidency,
}

pub enum TenantPlan {
    Free {
        max_sessions: u32,          // 3
        max_documents: u32,         // 100
        max_tokens_per_day: u64,    // 50_000
        models_allowed: Vec<String>, // ["magellano-77m"]
        max_agents: u32,            // 3 (macro-agents only)
    },
    Pro {
        max_sessions: u32,          // 50
        max_documents: u32,         // 10_000
        max_tokens_per_day: u64,    // 1_000_000
        models_allowed: Vec<String>, // ["magellano-77m", "magellano-3.3b"]
        max_agents: u32,            // 20
    },
    Enterprise {
        max_sessions: u32,          // unlimited
        max_documents: u32,         // unlimited
        max_tokens_per_day: u64,    // unlimited (pay-per-use)
        models_allowed: Vec<String>, // all models + custom fine-tuned
        max_agents: u32,            // 500+
        dedicated_resources: bool,  //  GPU dedicated pool
        sla_uptime_pct: f32,       // 99.9%
    },
}

pub struct ResourceQuotas {
    pub storage_bytes: u64,         // max storage per tenant
    pub compute_seconds_per_day: u64,
    pub api_requests_per_minute: u32,
    pub concurrent_tasks: u32,
}

pub enum DataResidency {
    EU,          // data stored in EU only
    US,          // data stored in US only
    Global,      // no geographic constraints
}
```

### K.3 Isolation Enforcement

#### K.3.1 Data Isolation

```rust
/// Every storage access is prefixed with tenant_id
/// Enforcement is handled by the middleware, not by agents

pub struct TenantAwareStateManager {
    inner: StateManager,
    tenant_id: String,
}

impl TenantAwareStateManager {
    /// All keys are automatically prefixed
    pub async fn get<T: DeserializeOwned>(&self, key: &str) -> Result<Option<T>> {
        let namespaced_key = format!("tenant:{}:{}", self.tenant_id, key);
        self.inner.get(&namespaced_key).await
    }
    
    pub async fn set<T: Serialize>(&self, key: &str, value: &T) -> Result<()> {
        let namespaced_key = format!("tenant:{}:{}", self.tenant_id, key);
        self.inner.set(&namespaced_key, value, None).await
    }
}

/// Vector Store: collection separate per tenant
/// tenant_a_embeddings, tenant_b_embeddings, ...

/// Knowledge Graph: tenant label on every node
/// (:Entity {tenant_id: "org_acme"}) — queries always filter by tenant

/// MongoDB: separate database per tenant
/// aios_tenant_a, aios_tenant_b, ...
```

#### K.3.2 Compute Isolation

```rust
/// Rate limiter per tenant — token bucket per API + inference
pub struct TenantRateLimiter {
    buckets: DashMap<String, TokenBucket>,
}

impl TenantRateLimiter {
    pub fn check(&self, tenant_id: &str, cost: u64) -> Result<()> {
        let bucket = self.buckets.get(tenant_id)
            .ok_or(RateLimitError::UnknownTenant)?;
        
        if !bucket.try_consume(cost) {
            return Err(RateLimitError::QuotaExceeded {
                tenant_id: tenant_id.to_string(),
                remaining: bucket.remaining(),
                reset_at: bucket.reset_time(),
            });
        }
        Ok(())
    }
}

/// Inference isolation: fair scheduling tra tenant
/// - No tenant can monopolize the GPU
/// - Weighted fair queuing based on the tenant plan
/// - Enterprise with dedicated_resources: separate GPU pool
pub struct FairInferenceScheduler {
    queues: HashMap<String, PriorityQueue<InferenceRequest>>,
    weights: HashMap<String, f32>,  // Enterprise=10, Pro=3, Free=1
}
```

#### K.3.3 Agent Isolation

```rust
/// Every tenant session has logically isolated agents
/// Agents share the same binary but have:
/// 1. TenantContext injected at startup (not modifiable by the agent)
/// 2. System prompt tenant-specific (brand voice, policies)
    /// 3. Tool access list filtered by plan
/// 4. Separate KV cache (no cross-tenant cache leakage)

pub struct TenantAgentFactory {
    pub fn create_agent(&self, tenant: &TenantContext, agent_type: AgentType) 
        -> Result<Box<dyn Agent>> 
    {
        let agent = match agent_type {
            AgentType::Planner => PlannerAgent::new(),
            AgentType::Executor => ExecutorAgent::new(),
            // ...
        };
        
        // Inject tenant context (immutable)
        agent.set_tenant_context(tenant.clone());
        
        // Restrict tool access based on plan
        let allowed_tools = self.get_allowed_tools(&tenant.plan);
        agent.set_tool_whitelist(allowed_tools);
        
        // Inject tenant-specific system prompt
        let system_prompt = self.load_tenant_prompt(&tenant.tenant_id);
        agent.set_system_prompt(system_prompt);
        
        Ok(agent)
    }
}
```

### K.4 Metering & Billing

```rust
/// Every billable operation emits a MeteringEvent
pub struct MeteringEvent {
    pub tenant_id: String,
    pub timestamp: DateTime<Utc>,
    pub event_type: BillableEvent,
    pub quantity: f64,
    pub unit: String,
}

pub enum BillableEvent {
    InferenceTokens { model: String, input_tokens: u32, output_tokens: u32 },
    StorageBytes { tier: String, delta_bytes: i64 },
    ApiRequests { endpoint: String },
    DocumentIngested { size_bytes: u64, chunks_created: u32 },
    ComputeSeconds { agent_type: String },
}

/// Metering flushed every 60 seconds to MongoDB collection "billing"
/// Daily aggregation for billing
///
/// Pipeline:
/// 1. Agent/Service emette MeteringEvent → NATS "metering.>"
/// 2. Metering Worker aggregates in memory (per-tenant counters)
/// 3. Every 60s: flush to MongoDB "billing.{tenant_id}.{YYYY-MM}"
/// 4. Billing service generates monthly invoice
```

### K.5 Onboarding Flow

```
1. Admin creates tenant via API → generates tenant_id, API key
2. System creates:
   - Collection Vector Store: "tenant_{id}_embeddings"
   - Database MongoDB: "aios_tenant_{id}"
   - Redis prefix: "tenant:{id}:*"
   - KG label: tenant_id on all nodes
   - NATS subject filter: "tenant.{id}.>"
3. Admin configura:
   - Plan (Free/Pro/Enterprise)
   - Data residency
   - Custom system prompts (opzionale)
   - Allowed models e tools
4. Tenant users receive JWT with claims: {tenant_id, user_id, role}
5. Every request → JWT verification → TenantContext injection → processing
```

---

## PART L: ACCESSIBILITY (GAP-10)

### L.1 Principles

AI OS is not just a backend — it has an Interface Agent that communicates with the user. Accessibility is a design requirement, not a retrofit.

Target: **WCAG 2.1 Level AA** for all user-facing outputs.

### L.2 Accessibility Domains

```
┌──────────────────────────────────────────────────────────────────┐
│                    ACCESSIBILITY DOMAINS                          │
│                                                                   │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐     │
│  │  INPUT          │  │  PROCESSING    │  │  OUTPUT         │     │
│  │  MODALITIES     │  │  ADAPTATION    │  │  MODALITIES     │     │
│  ├────────────────┤  ├────────────────┤  ├────────────────┤     │
│  │ Text (keyboard) │  │ Language       │  │ Text (screen   │     │
│  │ Voice (STT)     │  │ simplification │  │ reader compat) │     │
│  │ Gesture         │  │ Cognitive load │  │ Voice (TTS)    │     │
│  │ Eye tracking    │  │ reduction      │  │ Braille        │     │
│  │ Switch access   │  │ Error          │  │ Visual (high   │     │
│  │ Braille input   │  │ tolerance      │  │ contrast)      │     │
│  └────────────────┘  └────────────────┘  └────────────────┘     │
└──────────────────────────────────────────────────────────────────┘
```

### L.3 Interface Agent — Accessibility Layer

```rust
/// The Interface Agent has an AccessibilityAdapter sub-module
/// that transforms input and output based on the user's accessibility profile

pub struct AccessibilityProfile {
    pub screen_reader: bool,         // enables structured semantic output
    pub voice_input: bool,           // enables STT pipeline
    pub voice_output: bool,          // enables TTS pipeline
    pub high_contrast: bool,         // output con colori ad alto contrasto
    pub font_size: FontSize,         // Normal, Large, ExtraLarge
    pub language_level: LanguageLevel, // Standard, Simplified, Technical
    pub reduce_motion: bool,         // no animations in generated UIs
    pub cognitive_assistance: bool,  // detailed explanations, step-by-step guidance
}

pub enum FontSize {
    Normal,       // 14px
    Large,        // 18px
    ExtraLarge,   // 24px
}

pub enum LanguageLevel {
    Standard,     // output normale
    Simplified,   // short sentences, reduced vocabulary, no jargon
    Technical,    // specialized terminology, abbreviations
}
```

#### L.3.1 Screen Reader Compatibility

```rust
/// Every output from the Interface Agent includes semantic metadata
/// per screen reader (ARIA-like for CLI, semantic HTML for web)

pub struct AccessibleOutput {
    pub content: String,              // primary text content
    pub semantic_role: SemanticRole,  // heading, paragraph, list, table, code
    pub aria_label: Option<String>,   // description for screen readers
    pub aria_live: Option<String>,    // "polite", "assertive" for live updates
    pub reading_order: u32,           // explicit reading order
    pub alt_text: Option<String>,     // for generated images/charts
    pub summary: Option<String>,      // riassunto breve per skip navigation
}

pub enum SemanticRole {
    Heading { level: u8 },    // h1-h6
    Paragraph,
    List { ordered: bool },
    ListItem,
    Table,
    TableCaption,
    CodeBlock { language: String },
    Alert,                     // error or important notification
    Status,                    // status update
    Navigation,                // link/action
}

/// When the Executor generates code, the Critic verifies that:
/// 1. HTML tables have <caption> and scope on <th>
/// 2. Generated images have alt text
/// 3. Links are descriptive (no "click here")
/// 4. Colors have contrast ratio ≥ 4.5:1 (WCAG AA)
/// 5. Form elements have associated labels
```

#### L.3.2 Voice I/O Pipeline

```rust
/// STT (Speech-to-Text) pipeline in the Interface Agent
pub struct VoiceInputPipeline {
    stt_model: WhisperModel,        // local model for privacy
    vad: VoiceActivityDetector,     // avoids processing silence
    language_detector: LanguageDetector,
}

/// TTS (Text-to-Speech) pipeline in the Interface Agent
pub struct VoiceOutputPipeline {
    tts_model: TTSModel,           // Coqui TTS or equivalent local model
    ssml_builder: SSMLBuilder,     // Speech Synthesis Markup Language
    rate: f32,                     // speech rate (0.5-2.0)
    pitch: f32,                    // tono (customizable)
}

impl VoiceOutputPipeline {
    /// Converts text output to audio with SSML for correct pronunciation
    pub async fn speak(&self, output: &AccessibleOutput) -> AudioBuffer {
        let ssml = self.ssml_builder.build(output);
        // Pauses between sections, emphasis on titles, spelling for code
        self.tts_model.synthesize(&ssml).await
    }
}
```

#### L.3.3 Cognitive Assistance

```rust
/// When cognitive_assistance is active, the output is post-processed
pub struct CognitiveAssistant {
    simplifier: MagellanoTiny,  // rewrites for simplicity
}

impl CognitiveAssistant {
    pub async fn adapt(&self, output: &str, level: LanguageLevel) -> String {
        match level {
            LanguageLevel::Simplified => {
                // Prompt: "Rewrite this text using short sentences (max 15 words),
                // simple vocabulary, no metaphors, no technical abbreviations.
                // Maintain all important information."
                self.simplifier.rewrite(output, "simplified").await
            },
            LanguageLevel::Standard => output.to_string(),
            LanguageLevel::Technical => output.to_string(), // already technical
        }
    }
}
```

### L.4 Implementation Checklist

**Phase α (P0 — must have):**
- Textual output with semantic roles (heading, paragraph, list, code)
- Automatic alt text for generated images (via Magellano description)
- Keyboard-only navigation for CLI
- Human-readable error messages (no raw stack traces to users)
- High contrast mode for HTML/Markdown output

**Phase β (P1 — should have):**
- Voice input via Whisper (local)
- Voice output via TTS
- Language simplification via Magellano Tiny
- ARIA labels for web UI
- Explicit reading order

**Phase γ (P2 — nice to have):**
- Braille output support
- Eye tracking integration
- Switch access support
- Multi-language TTS (IT, EN, FR, DE, ES)
- Cognitive load estimation and automatic adaptation

### L.5 Accessibility Testing

```rust
/// The Critic Agent includes an AccessibilityChecker
pub struct AccessibilityChecker {
    wcag_rules: Vec<WCAGRule>,
}

impl AccessibilityChecker {
    pub fn validate_output(&self, output: &AccessibleOutput) -> Vec<A11yIssue> {
        let mut issues = vec![];
        
        // Check 1: images have alt text
        if output.semantic_role == SemanticRole::Image && output.alt_text.is_none() {
            issues.push(A11yIssue::new("1.1.1", "Missing alt text", Severity::Error));
        }
        
        // Check 2: heading hierarchy (no skip from h1 to h3)
        // Check 3: color contrast ratio ≥ 4.5:1
        // Check 4: link text is descriptive
        // Check 5: tables have caption and headers
        // Check 6: no color-only for conveying information
        
        issues
    }
}

/// The check is automatic: every output from the Interface Agent 
/// passes through the AccessibilityChecker before delivery
/// If severity == Error, the Critic requests revision from the Executor
```

---



ewpage


## APPENDIX: COMPLETE DELIVERABLE SUMMARY (v1-v4)

### v1 — Foundation
| Deliverable | Resolves | Content |
|-------------|---------|-----------|
| 3-Tier Taxonomy | GAP-11 | Macro (5-20), Meso (50-500), Micro (1K-4M+) |
| Agent Identity Schema | GAP-11 | `{tier}.{type}.{instance_id}@{zone}` |
| Inference HAL Trait | GAP-13 | `InferenceBackend` Rust trait, 7 methods |
| Model Router | GAP-13 | 4 routing policies + fallback chain |
| 5 Sequence Diagrams | E2E | Happy, Error, Learning, Collaboration, Hot-Swap |

### v2 — Contracts & Decisions
| Deliverable | Resolves | Content |
|-------------|---------|-----------|
| Bus 1: Control (gRPC) | API | 5 complete Protobuf services |
| Bus 2: Data (NATS) | API | Subject hierarchy + JSON-RPC 2.0 |
| Bus 3: Tensors (SharedMem) | API | Binary header 48B + TensorHandle zero-copy |
| Data Model (4 tiers) | State | Working Memory → Vector → KG → Persistent |
| ADR-001 to ADR-004 | Architecture | Rust+Swift, Agent-per-resource, Magellano+HAL, Gossip+Raft |

### v3 — Operations & Security
| Deliverable | Resolves | Content |
|-------------|---------|-----------|
| Observability Platform | GAP-01 | Prometheus+Thanos, OTel+Jaeger, Loki, 4 dashboards, 6 alerts |
| Security Threat Model | Security | 10 threats, 4-layer prompt injection defense, Zero Trust |
| Deployment Strategy | GAP-04 | Phase α Docker Compose → β K3s → γ Enterprise |
| CI/CD Pipeline | GAP-04 | GitHub Actions, SAST, SBOM, benchmarks |

### v4 — Data, Tenancy & Accessibility
| Deliverable | Resolves | Content |
|-------------|---------|-----------|
| Data Pipeline (CQRS) | GAP-03 | Event sourcing on NATS JetStream, 3 processing stages |
| Schema Evolution | GAP-03 | Backward-compatible, upcaster, registry |
| Multi-Tenancy Model | GAP-05 | Shared infrastructure / isolated data, namespace prefixing |
| Tenant Plans & Quotas | GAP-05 | Free/Pro/Enterprise, rate limiting, fair scheduling |
| Metering & Billing | GAP-05 | Event-driven metering, daily aggregation |
| Accessibility (WCAG AA) | GAP-10 | Screen reader compat, Voice I/O, cognitive assistance |
| A11y Testing | GAP-10 | AccessibilityChecker in the Critic Agent |

---

## GAP STATUS: ALL RESOLVED ✅

| GAP | Status | Resolved in |
|-----|-------|------------|
| GAP-01 | ✅ | v3 — Observability Platform |
| GAP-03 | ✅ | v4 — Data Pipeline CQRS + Event Sourcing |
| GAP-04 | ✅ | v3 — Deployment Strategy |
| GAP-05 | ✅ | v4 — Multi-Tenancy Model |
| GAP-10 | ✅ | v4 — Accessibility WCAG AA |
| GAP-11 | ✅ | v1 — 3-Tier Taxonomy |
| GAP-12 | ✅ | v2 — ADR-003 Magellano boundary |
| GAP-13 | ✅ | v1 — Inference HAL |

**The AI OS architecture is now fully specified.**

**Recommended next steps:**
1. **Consolidation** — Single v5 document unifying v1-v4 into a complete Technical Design Document
2. **Phase α Sprint Planning** — Breakdown of the first 6 sprints with user stories and acceptance criteria
3. **Proof of Concept** — Minimal Rust prototype of the Kernel + 1 macro-agent (Planner) + Control Bus
4. **Benchmark Baseline** — Establish measurable target metrics for the PoC
