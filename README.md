# AI OS Architecture

> **Status:** Architecture Whitepaper · PoC in progress · Rust/Swift contributors welcome

An AI-native Operating System that treats agents as kernel processes, not chat prompts.

---

## Architecture Overview — TDD v5.1

<img width="1310" height="617" alt="image" src="https://github.com/user-attachments/assets/ec33f241-409f-47cf-9048-8f937e0a78a2" />


*Full architecture — all GAPs resolved. Agent Registry, 3-Bus communication, Observability, Zero Trust Security, Multi-Tenancy, and the QLoRA self-improvement loop — all integrated.*

---

## Why This Exists

In 2025, the state-of-the-art for working with AI agents looked like this:

```
.claude/agents/
├── engineering/
│   ├── frontend-developer.md
│   └── backend-architect.md
└── testing/
    └── api-tester.md
```

You manually create `.md` files for each "role", ask Claude to read a plan before coding, clean context between sessions, and fix prompts by hand when the agent makes mistakes.

These are good heuristics. They are also **artisanal workarounds** for the absence of a real system.

**AI OS replaces every one of those workarounds with a protocol.**

---

## The 8 Rules vs. The OS

| Manual Approach (2025 Best Practice) | AI OS (Magellano Architecture) |
|--------------------------------------|-------------------------------|
| Create a `.md` file per agent role | 3-Tier Taxonomy (Macro/Meso/Micro) — agents spawn dynamically from Registry |
| Ask Claude to "plan first" | Planner Agent generates a mathematical DAG before any execution |
| Maintain `CLAUDE.md` for project memory | 4-Layer State: Working Memory → Vector Store → Knowledge Graph (Neo4j) → Persistent Store |
| Write "Constraints" sections in prompts | Zero Trust Security + ED25519-signed messages + Sandbox execution (Docker/Wasm) |
| Open a new chat to "clean context" | Session State managed by Kernel — KV cache allocated/deallocated automatically |
| Separate test agent from coding agent | Critic Service integrated in execution loop — output blocked if Quality Score < 0.85 |
| Human does the git commit | Escalation Policy: system self-recovers, escalates to human only for Tier 1 decisions |
| Fix the `.md` file when agent fails | **Nightly QLoRA fine-tuning loop — model retrains on its own errors while you sleep** |

The last row is the gap that matters most. The manual approach requires a human to notice the error, open a file, write a correction, and hope it generalizes. The OS collects feedback during the session, builds a training batch, and fine-tunes the base model overnight. The next morning, the error no longer exists — in the weights.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                      AI OS KERNEL (Rust)                │
│                                                         │
│   ┌─────────────┐    ┌──────────────────────────────┐   │
│   │Task Scheduler│   │   Agent Swarm Orchestrator   │   │
│   │Resource Mgr │◄──►│  Planner · Executor · Critic     │
│   │Context Mgr  │    │  Memory  · Interface Agent   │   │
│   │Model Loader │    └──────────────────────────────┘   │
│   │Tool Registry│              │                        │
│   └─────────────┘    ┌─────────▼──────────────────────┐ │
│                      │       3-Bus Communication      │ │
│                      │  gRPC(1-10ms) · NATS(10-100ms) │ │
│                      │  SharedMem(<1µs · zero-copy)   │ │
│                      └────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
         │ Metal API / CoreML
┌────────▼────────────────────────────────────────────────┐
│              Magellano Inference Engine (Swift)         │
│  3.3B params · Apple Silicon · NF4 quant · 50-100ms     │
│  QLoRA nightly loop · A/B gate (≥5%) · Hot-swap deploy  │
└─────────────────────────────────────────────────────────┘
```

### What Changed vs. the Original HLD

The initial HLD showed 5 kernel services + 5 agents + a generic "Shared Message Bus". During TDD development, 8 architectural gaps were identified and resolved:

| Gap | What was missing | Resolution |
|-----|-----------------|------------|
| GAP-01 | No observability platform | Prometheus+Thanos, OTel+Jaeger, Loki, Grafana — 6 SLO alerts |
| GAP-03 | No data pipeline | CQRS + Event Sourcing on NATS JetStream, 3 processing stages |
| GAP-04 | No deployment strategy | Phase α Docker Compose → β K3s → γ Enterprise, GitHub Actions CI/CD |
| GAP-05 | No multi-tenancy | Namespace isolation, Free/Pro/Enterprise plans, event-driven billing |
| GAP-10 | No accessibility | WCAG AA, Voice I/O, AccessibilityChecker in Critic Agent |
| GAP-11 | "Agents" was a flat list | 3-Tier Taxonomy: Macro (5) → Meso (6) → Micro (millions) + Agent Registry |
| GAP-12 | Magellano boundary undefined | ADR-003: clear Rust↔Swift contract via InferenceBackend HAL trait |
| GAP-13 | No inference abstraction | `InferenceBackend` Rust trait (7 methods), 4 routing policies, fallback chain |

---

### Core Design Decisions

**Rust Kernel** — Memory safety without GC, predictable latency, native async with Tokio. The kernel orchestrates agents as processes, not chat turns.

**Swift + Metal Inference (Magellano)** — Native Apple Silicon execution. Inference latency ~50-100ms on M-series. 3.3B parameters, NF4 quantized (6.6GB → 1.7GB RAM).

**FIPA-ACL over gRPC** — Agents communicate via a formal Agent Communication Language. Every message is typed, versioned, and ED25519-signed. No prompt injection possible at the protocol layer.

**3-Bus Architecture** — Control traffic (gRPC, 1-10ms), data/results (NATS, 10-100ms), tensor/embeddings (Shared Memory, <1µs zero-copy DMA). Mixing these causes head-of-line blocking — they are strictly separated.

**4-Layer Memory** — Context retrieval uses semantic RAG (dense + sparse FAISS, top-K=5, reranked in ~80ms total), not file reads. The Knowledge Graph (Neo4j) stores relationships that flat vector search cannot represent.

**Critic-in-the-Loop** — No output leaves the system without a Quality Score ≥ 0.85 across 5 weighted dimensions. The Critic is not a prompt; it is a kernel service with veto power.

**Two-Loop Learning**
- *Fast loop*: Feedback updates Vector Store and KG in-session (real-time)
- *Slow loop*: Nightly QLoRA training (rank 16, 7 target modules, ~0.5% trainable parameters) → ~35MB adapter → A/B gate (≥5% improvement required) → hot-swap, zero downtime

---

## Performance Targets (TDD v5.1)

| Phase | Component | Duration |
|-------|-----------|----------|
| Input parse | Interface Agent | 15ms |
| Registry lookup | Agent Registry | 5ms |
| RAG retrieval | Memory Agent | ~80ms |
| Planning (DAG) | Planner Agent | ~180ms |
| Inference | Magellano / Metal | 50–100ms |
| Validation | Critic Service | ~120ms |
| Execution + output | Executor Agent | ~4.3s |
| **TOTAL E2E** | **Happy path** | **~4.8s** |
| Nightly QLoRA | Full cycle | ~45min |

---

## Repository Structure

```
/
├── README.md
├── CONTRIBUTING.md
├── docs/
│   ├── AI_OS_TDD_v5_1.md                       # Full Technical Design Document 
                                                  (Sequence diagrams: timing, error   recovery, QLoRA loop)
│   └── ADR/                                    # Architecture Decision Records (ADR-001 to ADR-004)
├── diagrams/
│   ├── ai_os_manifesto_v51.html                # ← Full v5.1 architecture (this README's header)
│   ├── ai_os_architecture.png                  # Original HLD (pre-gap-resolution reference)
│   ├── ai_os_kernel_exploded.png
│   ├── ai_os_agent_swarm_orchestrator.png
│   ├── ai_os_security_layer.png
│   ├── ai_os_memory_agent.png
│   └── *.html                                  # Interactive Mermaid viewers
└── poc/                                        # (in progress) Rust kernel skeleton
```

---

## Current Status

| Component | Status |
|-----------|--------|
| Architecture (TDD v5.1) | ✅ Complete ~ 4600+ lines |
| 8 GAPs identified and resolved | ✅ All closed |
| Sequence Diagrams (5 scenarios) | ✅ Complete — Addendum C.1–C.4 |
| ADR-001÷004 | ✅ Complete |
| QLoRA Learning Path | ✅ Complete |
| Multi-Tenancy model | ✅ Complete |
| Security Threat Model (10 threats) | ✅ Complete |
| Rust Kernel PoC | 🔄 In progress |
| Magellano Swift inference | 🔄 Design phase |
| Integration tests | ⏳ Pending PoC |

---

## Contributing

Looking for contributors with experience in:
- **Rust** (async, Tokio, tonic/gRPC) — Kernel and orchestration layer
- **Swift + Metal / CoreML** — Magellano inference engine
- **FIPA-ACL / multi-agent systems** — Protocol implementation

Read `CONTRIBUTING.md` before opening issues. The TDD v5.1 is the source of truth — start from the relevant section and open a discussion issue before implementing.

---

## License

Architecture documentation: Creative Commons BY-SA 4.0  
Code (when published): Apache 2.0

---
---
## Author
Alessandro La Gamba
Senior System Engineer | AI/ML Researcher
25+ years experience || distributed systems and edge AI

---

Version: v1 | Status: DEV | February 2026
*"The best prompt engineering is no prompt engineering."*
