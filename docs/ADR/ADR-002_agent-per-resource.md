# ADR-002: Agent-per-Resource vs Pooled Agents

**Status:** Accepted  
**Date:** 2026-02-17  
**Authors:** Alessandro + Claude (CoS)  
**Deciders:** Architecture team  

---

## Context

Two competing paradigms for Tier 3 micro-agents:

- **(A) Agent-per-resource:** One dedicated agent per hardware resource (page frame, CPU core, network connection) — as described in the Deep Analysis bio-inspired model
- **(B) Pooled agents:** A shared pool of worker agents managing resources dynamically, allocated on demand

The choice has deep implications for memory overhead, fault isolation, locality, and the feasibility of bio-inspired algorithms (ant colony scheduling, pheromone-based routing).

---

## Decision

**Agent-per-resource for Tier 3 (micro-agents), with controlled overhead and ephemeral lifecycle.**

---

## Rationale

### Why agent-per-resource

**Locality:** Each agent has affinity with the resource it manages → cache-friendly, NUMA-aware. A Page Agent always operates on the same physical frame, keeping it in L2/L3 cache.

**State simplicity:** Each agent knows only its own resource → no lock contention across resources. No global lock needed for page fault handling.

**Bio-inspired algorithms:** Ant colony scheduling and pheromone-trail routing *require* local agents. Pheromone evaporation and reinforcement happen at the resource level — pooled agents cannot maintain per-resource pheromone state efficiently.

**Fault isolation:** A crash of a single Page Agent affects only that 4KB frame. A pooled worker crash could corrupt multiple resource states simultaneously.

### Overhead is controlled

| Agent type | RAM/instance | Scale on 16GB | Total overhead | % RAM |
|------------|-------------|---------------|----------------|-------|
| Page Agent | 64 bytes | ~4M instances | 256 MB | 1.5% |
| Core Agent | 256 bytes | 16 cores | 4 KB | ~0% |
| Connection Agent | 128 bytes | ~10K active | 1.2 MB | <0.01% |
| Device Agent | 512 bytes | ~20 devices | 10 KB | ~0% |
| Buffer Agent | 32 bytes | ~slot count | proportional | <0.5% |
| Route Agent | 96 bytes | ~active routes | proportional | <0.1% |

**Total Tier 3 overhead on 16GB RAM: ~2%** — acceptable. Scales linearly with RAM (64GB → ~16M page agents, same percentage).

### When NOT to use agent-per-resource

Two explicit exceptions where agent-per-resource is inappropriate:

1. **Buffer Pool Manager:** Slot allocation requires a global view of the pool. A single Buffer Pool Manager agent handles all slots — it needs to see the full allocation bitmap to make optimal decisions.

2. **Route agents:** Created on-demand for *active* routes, not pre-allocated for all possible routes in the routing table. A routing table with 10M possible routes does not spawn 10M agents — only routes with active traffic get an agent.

---

## Consequences

**Positive:**
- Linear scalability: more RAM → proportionally more agents, same overhead percentage
- True fault isolation at resource granularity
- Enables ant colony optimization (ACO) for scheduling and routing
- Cache locality per resource improves performance in NUMA architectures

**Negative / Mitigations:**
- **Garbage collection:** Ephemeral agents must be created/destroyed efficiently → **arena allocator** recommended (pre-allocated slabs, O(1) alloc/free)
- **Monitoring:** Cannot trace 4M individual agents → aggregate metrics per zone/type (e.g., `page_fault_rate{numa_zone="0"}`, not per-agent)
- **Memory pressure during peak:** If all 4M page agents are active simultaneously, 256MB is reserved → acceptable given typical workload patterns

---

## Alternatives Rejected

| Alternative | Reason rejected |
|-------------|----------------|
| Pooled agents | More memory-efficient but loses locality; makes bio-inspired algorithms impossible (pheromone state requires per-resource agents) |
| Hybrid (pool for memory, dedicated for CPU/network) | Increases architectural complexity without clear benefit; two paradigms to maintain |
| Agent-per-resource with pre-allocation | Pre-allocating all possible agents at boot consumes too much RAM before they're needed; lazy creation preferred |

---

## Related

- ADR-004: Gossip+Raft consensus (Meso-level Registry Agent uses Gossip to track Tier 3 agent populations)
- TDD v5.1, Parte A.4–A.5: Full Tier 2 and Tier 3 taxonomy with instance counts
- TDD v5.1, Parte A.6: Cross-tier communication rules (Tier 1→Tier 3 never direct; always via Tier 2 aggregation)
