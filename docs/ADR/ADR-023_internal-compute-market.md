# ADR-023: Internal Compute Market — Auction-Based Resource Allocation

**Status:** Proposed (v5.2)  
**Date:** 2026-02-26  
**Authors:** Alessandro La Gamba  
**Deciders:** Architecture team  

---

## Context

On a dense edge deployment (Mac Studio, 50+ concurrent agents, M2 Ultra with 24 GPU cores), static priority queues for GPU/ANE slot allocation create systematic unfairness and inefficiency:

- **Priority inversion:** A low-priority background scan holds a GPU slot while a user-facing inference request waits
- **Hardcoded priorities age poorly:** A static `priority = 7` for the QLoRA trainer was correct in Q1 but wrong in Q4 (training more urgent during model regression)
- **No economic signal:** Agents cannot express "I really need this slot right now" vs "I can wait"
- **Battery waste:** On battery-constrained devices, all agents compete equally regardless of their deadline urgency

The insight: compute slots have value that varies dynamically. Market mechanisms are efficient at allocating scarce resources with heterogeneous demand.

Three allocation models were evaluated:
- **Option A:** Static priority queue (current v5.1 approach)
- **Option B:** Fair-share scheduler (equal allocation + burst)
- **Option C:** Credit-based internal auction (market mechanism)

---

## Decision

**Credit-based internal auction: every 100ms, the Auctioneer Service (Rust kernel) auctions available GPU/ANE slots. Agents bid internal credits. Highest bids win. Anti-starvation mechanism accumulates credits for losing agents.**

```
┌─────────────────────────────────────────────────────────────────────┐
│                    INTERNAL COMPUTE MARKET                          │
│                                                                     │
│  Every 100ms:                                                       │
│                                                                     │
│  ┌─────────────┐   auction_request    ┌─────────────────────────┐  │
│  │  Auctioneer │ ◄──────────────────── │  Agent Bidding System   │  │
│  │  Service    │                       │                         │  │
│  │  (Rust)     │    {agent_id,         │  Each agent has:        │  │
│  │             │     slot_type,        │  - Credit wallet (OCaml │  │
│  │             │     credits_bid,      │    STM atomic)          │  │
│  │             │     deadline_ms}      │  - Spend policy (Lua)   │  │
│  └──────┬──────┘                       └─────────────────────────┘  │
│         │                                                            │
│         │ determine winners (sealed-bid second-price)                │
│         │                                                            │
│         ▼                                                            │
│  ┌──────────────┐                                                    │
│  │  Slot Grant  │  → notify winners via Bus 1 (gRPC)                │
│  │  + Credit    │  → deduct winning bid from wallet                  │
│  │  Settlement  │  → add anti-starvation bonus to losers            │
│  └──────────────┘                                                    │
└─────────────────────────────────────────────────────────────────────┘
```

### Auction Mechanism: Sealed-Bid Second-Price (Vickrey)

Second-price (pay the second-highest bid) is used because:
- **Truthful bidding is dominant strategy:** No agent benefits from strategic under/over-bidding
- **Simple to implement:** One round, no iterative bidding
- **Efficient allocation:** Slot goes to the agent that values it most

```rust
pub struct AuctionResult {
    winner:         AgentId,
    allocation:     SlotAllocation,
    clearing_price: u64,     // second-highest bid
    round_id:       u64,
}

fn run_auction(bids: Vec<AgentBid>, available_slots: u32) -> Vec<AuctionResult> {
    let mut sorted_bids = bids.clone();
    sorted_bids.sort_by(|a, b| b.credits.cmp(&a.credits)); // descending

    sorted_bids.iter().take(available_slots as usize).enumerate().map(|(i, bid)| {
        let clearing_price = sorted_bids.get(i + 1)
            .map(|next| next.credits)
            .unwrap_or(0); // last winner pays 0 (no competition)

        AuctionResult {
            winner:         bid.agent_id,
            allocation:     SlotAllocation::GpuCore { duration_ms: 100 },
            clearing_price,
            round_id:       self.round_id,
        }
    }).collect()
}
```

### Credit System

```rust
pub struct AgentWallet {
    balance:  AtomicU64,      // credits (STM atomic — no contention)
    earned:   u64,            // total earned this session
    spent:    u64,            // total spent this session
    policy:   SpendPolicy,    // Lua-sandboxed policy script
}

/// Anti-starvation: losing agents accumulate credits over time
/// so they can eventually outbid continuous winners
pub fn apply_starvation_bonus(losers: &[AgentId], wallets: &mut HashMap<AgentId, AgentWallet>) {
    for agent_id in losers {
        let wallet = wallets.entry(*agent_id).or_default();
        let bonus = (wallet.rounds_without_slot * 2).min(50); // cap at 50 credits/round
        wallet.balance.fetch_add(bonus, Ordering::Relaxed);
        wallet.rounds_without_slot += 1;
    }
}
```

### Default Credit Allocations

| Agent Type | Starting Credits | Earn Rate (credits/task) | Max Bid |
|------------|-----------------|-------------------------|---------|
| Safety Monitor | 10,000 | 500 | Unlimited |
| User-Facing Inference | 1,000 | 300 | 1,000 |
| QLoRA Trainer | 500 | 200 | 500 |
| Background Analytics | 100 | 20 | 200 |
| Logging/Metrics | 50 | 5 | 100 |

### Spend Policy (Lua, sandboxed in WASM)

```lua
-- Example: QLoRA Trainer spend policy
function should_bid(context)
  -- Never bid during business hours (user latency priority)
  if context.hour >= 9 and context.hour <= 18 then
    return false
  end
  -- Bid aggressively after midnight
  local urgency = context.training_backlog / 100  -- 0.0 to 1.0
  local bid = math.floor(200 * urgency)
  return bid > 0, bid
end
```

---

## Rationale

### Why market over static priority

Static priorities require human configuration and become stale. The market mechanism **self-adjusts**: if training is behind schedule, the QLoRA trainer naturally bids more (it has accumulated credits). If a user starts an urgent query, the inference agent bids more. No configuration change needed.

### Why 100ms auction interval

- Shorter (10ms): too much scheduling overhead; agent state changes too fast for useful bids
- Longer (1000ms): too coarse for burst workloads; user perceives latency spikes
- 100ms: matches the Magellano inference window and the ZK batch cycle (ADR-013)

### Why Vickrey (second-price) over first-price

First-price auctions require agents to strategically shade their bids — complex for agents to optimize. Vickrey auctions have a dominant truthful strategy: bid exactly your true value. This simplifies agent design and reduces gaming.

### Why Lua for spend policies

- **Sandboxed execution** (WASM runtime) — a buggy policy cannot crash the kernel
- **Hot-reloadable** — spend policies can be updated without agent restart
- **Simple syntax** — operators can write policies without Rust/Haskell expertise

---

## Consequences

**Positive:**
- Dynamic allocation self-adjusts to workload changes without configuration
- Safety-critical agents (Safety Monitor) always win via high starting credits
- Anti-starvation prevents background agents from being indefinitely blocked
- Spend policies are hot-reloadable and operator-visible

**Negative / Mitigations:**
- **100ms overhead per agent per round:** With 500 meso-agents, that is 500 bids/100ms = 5,000 bids/second → *handled by Rust Auctioneer in O(n log n) sort; benchmarked at <2ms for 1,000 bids*
- **Credit economy requires bootstrapping:** New agents have no history → *solved by default credit allocations + quick credit accumulation from first tasks*
- **Spend policies can be poorly written:** Lua errors in policy → *WASM sandbox catches panics; fallback to `bid = default_bid` on any Lua error*

---

## Alternatives Rejected

| Alternative | Reason rejected |
|-------------|----------------|
| Static priority queue | Requires manual tuning; stale over time; no economic signal |
| Fair-share scheduler (CFS-style) | Treats all tasks as equally valuable; no urgency signal |
| Token bucket rate limiting | Limits throughput but doesn't optimize allocation across competing agents |
| Kubernetes-style resource requests/limits | Too coarse (per-pod, not per-100ms slot); requires static declarations |
| Real-money billing | Unnecessary complexity; internal credits suffice for intra-node allocation |

---

## Related

- ADR-002: Agent-per-Resource — defines the population of bidders (Tier 1-3 agents)
- ADR-025: Adaptive Energy Governance — Power Governor can override auction results during Power Save mode
- ADR-030: Federated Constellation — a cross-node version of this market (inter-OS credit clearing)
- TDD v5.1, Parte A.3: Resource Manager — integrates with Auctioneer Service
