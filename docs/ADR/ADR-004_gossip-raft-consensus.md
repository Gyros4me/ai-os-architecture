# ADR-004: Gossip vs Raft vs PBFT for Consensus

**Status:** Accepted  
**Date:** 2026-02-17  
**Authors:** Alessandro La Gamba  
**Deciders:** Architecture team  

---

## Context

A multi-agent system with potentially millions of Tier 3 agents, hundreds of Tier 2 agents, and 5 Tier 1 agents requires consensus mechanisms for four distinct problems:

1. **Service discovery** — Which agents are alive? What are their capabilities? Where are they?
2. **Leader election** — Which Planner Agent is currently active? Which Consensus Agent leads the quorum?
3. **Post-failure replan** — After a node crash, agents must agree on DAG state and resume correctly
4. **Checkpoint coordination** — Distributed snapshot (Chandy-Lamport variant) requires all agents in scope to agree on the cut

Three protocols were evaluated against all four requirements.

---

## Protocol Comparison

| Criterion | Gossip (SWIM) | Raft | PBFT |
|-----------|--------------|------|------|
| **Consistency** | Eventual (~100ms convergence) | Strong (linearizable) | Strong (linearizable) |
| **Latency** | High (gossip rounds) | Low (~10ms) | Medium (~50ms, extra round-trips) |
| **Scalability** | Excellent — O(log N) propagation | Good — up to ~7 nodes practical | Poor — O(N²) message complexity |
| **Fault tolerance** | Up to 50% node failure | Up to 49% node failure (f < N/2) | Up to 33% Byzantine nodes (f < N/3) |
| **Implementation complexity** | Low | Medium | High |
| **Ideal use case** | Membership, health, metadata | Leader election, replicated state machine | Byzantine fault tolerance |
| **Crate/library** | Custom SWIM or `memberlist` port | `openraft` (Rust, production-ready) | No mature Rust implementation |

---

## Decision

**Hybrid approach: Gossip (SWIM protocol) for service discovery and health monitoring; Raft for leader election and critical coordination.**

```
GOSSIP (SWIM protocol) handles:
├── Agent Registry: membership propagation, capability advertising
├── Health Monitoring: heartbeat, failure detection, suspicion mechanism
├── Metric aggregation: distributed averaging (agent counts, load, temperature)
└── Configuration propagation: feature flags, routing policy updates

RAFT (openraft crate) handles:
├── Planner Leader Election: exactly one active Planner per availability zone
├── Checkpoint Coordination: 3-phase commit for Chandy-Lamport snapshots
├── DAG State Machine: DAG execution state replicated across 3 nodes
└── Model Router Consensus: agreement on active backend configuration
```

---

## Rationale

### Why not Gossip alone

Gossip provides *eventual* consistency — convergence typically in 100–500ms depending on cluster size. This is acceptable for membership and health data where stale-by-100ms is harmless.

It is **not acceptable** for:
- Leader election (two Planners believing they are both leader → conflicting DAGs)
- Checkpoint coordination (split snapshot → recovery from corrupted state)
- DAG state machine (two agents acting on divergent DAG state)

These require **strong consistency** (linearizability) which Gossip cannot provide.

### Why not Raft alone

Raft's consensus quorum is O(N) messages per round and requires a dedicated leader. This scales well to 7 nodes but becomes expensive at 500+ Meso-agents (all competing for the same Raft log would serialize every operation).

The Registry Agent alone must track potentially thousands of Tier 3 agent instances. Putting every heartbeat through a Raft log would saturate the leader with writes.

Gossip, by contrast, propagates membership changes in O(log N) rounds with no single leader — it is the right tool for high-frequency, low-precision health data.

### Why not PBFT

PBFT provides Byzantine fault tolerance — it can handle nodes that actively lie or send conflicting messages. The AI OS does not have Byzantine requirements:

- All agents run within the same deployment boundary (same trust domain)
- No external untrusted nodes participate in consensus
- The threat model (see TDD v5.1, Parte H — Security) identifies prompt injection and data exfiltration as threats, not Byzantine agent behavior
- PBFT message complexity is O(N²) per consensus round — at 20 Meso-agents, that is 400 messages per decision

PBFT would be correct but massively over-engineered for a trusted-deployment environment.

---

## Hybrid Implementation

### Gossip tier (SWIM protocol)

```
Each agent runs SWIM:
- Every T_gossip ms: select k random peers, send PING
- If no ACK within T_ping: send PING-REQ to m indirect probes  
- If still no ACK: mark as SUSPECT, broadcast via gossip
- After T_suspect timeout: mark as FAILED, remove from registry

Parameters (tunable):
  T_gossip = 200ms    (gossip interval)
  T_ping   = 50ms     (direct ping timeout)
  k        = 3        (fanout factor)
  m        = 3        (indirect probe count)
  T_suspect = 2s      (suspicion timeout before FAILED)
```

Membership updates (JOIN, LEAVE, FAILED) are piggybacked on gossip messages. No dedicated broadcast channel needed.

### Raft tier (openraft)

```
Raft cluster per concern:
- PlannersRaft:   3 nodes (active Planner + 2 standbys)
- CheckpointRaft: 3 nodes (State Agents in snapshot scope)
- RouterRaft:     3 nodes (Model Router configuration)

Operations requiring Raft consensus:
- Planner takeover after failure: new leader elected in <500ms
- Checkpoint initiation: PRE_COMMIT → snapshot → COMMIT (3 phases)
- DAG replan: post-failure state reconstruction via log replay
```

openraft provides: async Rust, customizable storage backend, membership change without downtime, leader lease reads.

---

## Consequences

**Positive:**
- Gossip scales to millions of Tier 3 agents without any leader bottleneck
- Raft provides the strong consistency needed for exactly-one semantics (one Planner, one checkpoint commit)
- `openraft` is production-ready, actively maintained, fully async — no implementation risk for the Raft layer
- Two protocols with orthogonal failure modes → defense in depth

**Negative / Mitigations:**
- **Two protocols to maintain:** each has its own failure modes and tuning knobs → *mitigated by clear separation of concerns (Gossip never used for strong-consistency decisions)*
- **Gossip false positives:** overly aggressive `T_ping` → healthy agents marked suspect → *mitigated by SWIM's indirect probing (m=3 before marking FAILED) and configurable T_suspect*
- **Raft cluster size limit:** practical limit ~7 nodes per Raft group → *not a problem: Raft groups are per-concern (3 nodes each), not system-wide*
- **No Byzantine protection:** insider threat within the deployment is not covered → *explicitly accepted; addressed in threat model (TDD v5.1, Parte H)*

---

## Alternatives Rejected

| Alternative | Reason rejected |
|-------------|----------------|
| Raft only | O(N) message cost per heartbeat unacceptable for 500+ Meso-agent membership tracking |
| Gossip only | Cannot provide strong consistency for leader election and checkpoint coordination |
| PBFT | O(N²) message complexity; no mature Rust implementation; Byzantine requirements not present in our threat model |
| etcd/Zookeeper | External dependency; operational overhead; not embeddable in Rust kernel without process boundary |
| Custom consensus | 6–12 months to implement and prove correct; openraft already exists and is proven |

---

## Related

- ADR-002: Agent-per-Resource (defines the population scale Gossip must handle: ~4M Tier 3 agents)
- TDD v5.1, Parte A.4: Meso-Agent Consensus Engine (the agent that wraps the Raft implementation)  
- TDD v5.1, Addendum C.2: Error Recovery — distributed partition scenarios that Raft must handle  
- TDD v5.1, Parte G: Observability — metrics for both Gossip (`aios_gossip_convergence_ms`) and Raft (`aios_raft_leader_election_ms`)

---

## Responding to "Why not just use a database for coordination?"

A database (PostgreSQL, Redis) with distributed locking is a valid pattern for small clusters. At AI OS scale:

1. **4M Tier 3 agents cannot all heartbeat to a single DB** — even at 1 heartbeat/second that is 4M writes/second, beyond any single-node DB
2. **The DB itself becomes a consensus problem** — you still need Raft or Paxos to replicate the DB across availability zones
3. **Gossip eliminates the "thundering herd"** — membership changes propagate via epidemic spread, not a central write point

The Gossip+Raft combination *is* the coordination layer. No additional database required for this concern.
