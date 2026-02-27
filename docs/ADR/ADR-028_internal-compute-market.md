# ADR-028: Internal Compute Market

**Status:** Proposed  
**Date:** 2026-02-26  
**Authors:** Alessandro La Gamba  
**Deciders:** Architecture team  

---

## Context

On a densely-loaded node (e.g. Mac Studio running 50+ concurrent agents), static priority queues for GPU/ANE slot allocation create two failure modes:

1. **Priority inversion at scale:** a low-priority batch job holds a GPU slot while a high-priority user-facing inference request queues behind it — the static priority system cannot express "I am willing to pay more to preempt this slot right now"
2. **Utilisation waste:** when high-priority agents are idle, low-priority agents cannot opportunistically claim the unused capacity without a heavyweight priority reconfiguration

A market mechanism allows agents to express the *economic value* of their compute need in real time, without requiring the kernel to maintain a global priority ordering across heterogeneous task types.

---

## Decision

**Implement an internal credit-based compute market with Dutch auctions every 100 ms for available GPU/ANE/CPU slots. Agents hold internal (non-monetary) credit wallets; safety-critical agents always win by having uncapped budgets; fairness is preserved by anti-starvation credit accrual.**

### Auctioneer Service

```rust
// kernel/src/market/auctioneer.rs

pub struct Auctioneer {
    slots:   Vec<ComputeSlot>,   // GPU/ANE/CPU slots available this tick
    bids:    BTreeMap<Credits, Vec<AgentId>>, // sorted descending
    history: NATSJetStream,      // immutable audit log
}

impl Auctioneer {
    /// Called every 100 ms by the kernel scheduler tick.
    pub fn run_auction(&mut self) {
        let bids = self.collect_bids_from_wallets();  // non-blocking, timeout 5 ms
        let assignments = self.dutch_auction(&bids, &self.slots);
        self.dispatch_assignments(assignments);
        self.history.append(&assignments);            // immutable market log
    }

    fn dutch_auction(
        &self,
        bids:  &BTreeMap<Credits, Vec<AgentId>>,
        slots: &[ComputeSlot],
    ) -> Vec<Assignment> {
        // Highest bid wins. Ties broken by agent_id lexicographic order (deterministic).
        // Anti-starvation: agents that have not won in > 30 ticks get a +50 credit bonus.
        let mut assignments = Vec::new();
        for slot in slots.iter() {
            if let Some(winner) = bids.iter().rev().find_map(|(_, agents)| agents.first()) {
                assignments.push(Assignment { agent: *winner, slot: *slot });
            }
        }
        assignments
    }
}
```

### Agent Credit Wallets

```ocaml
(* agents/lib/wallet.ml — OCaml STM for atomic credit transactions *)

type wallet = {
  mutable balance: int;
  mutable starvation_ticks: int;
}

let spend (w: wallet) (amount: int) : (unit, string) result =
  (* STM transaction: atomic debit, never negative *)
  Stm.atomically (fun () ->
    if w.balance >= amount then begin
      w.balance <- w.balance - amount;
      Ok ()
    end else
      Error "insufficient credits"
  )

let accrue_anti_starvation (w: wallet) : unit =
  (* Called by auctioneer when agent loses 30 consecutive auctions *)
  if w.starvation_ticks >= 30 then begin
    w.balance <- w.balance + 50;   (* starvation bonus *)
    w.starvation_ticks <- 0
  end
```

### Spend Policies (Lua/WASM Sandboxed)

Each agent type ships with a spend policy script that the Auctioneer evaluates before accepting a bid:

```lua
-- agents/planner/spend_policy.lua
function compute_bid(task_urgency, wallet_balance, slot_type)
  if task_urgency == "safety_critical" then
    return math.huge   -- always wins; uncapped
  elseif slot_type == "gpu" and task_urgency == "user_facing" then
    return math.min(wallet_balance * 0.4, 300)  -- up to 40% of wallet, max 300
  elseif task_urgency == "batch" then
    return math.min(wallet_balance * 0.05, 20)  -- frugal for background tasks
  end
end
```

### Slot Types and Default Budgets

| Slot Type | Capacity | Typical Users | Anti-Starvation Enabled |
|-----------|----------|---------------|------------------------|
| GPU (Metal) | 4 slots (Mac Studio M2 Ultra) | Magellano inference, QLoRA training | No — safety-critical always wins |
| ANE (Neural Engine) | 2 slots | Magellano 77M intent parsing, embeddings | Yes |
| CPU HiPri | 8 vCores | Planner (Haskell), Executor | Yes |
| CPU LoPri | 8 vCores | Background analytics, logging | Yes |

### Credit Issuance

Credits are issued by the kernel on a fixed schedule:
- **Per-agent daily allocation:** 10,000 credits/day, distributed as 1 credit/8.6 s
- **Task reward:** 5–50 bonus credits when a task completes with Critic score ≥ 0.9
- **Safety-critical override:** `SAFETY_CRITICAL_FLAG` bypasses the market entirely (no credits spent)

---

## Rationale

**Why a market (not priority queues with preemption):**  
Priority queues require a global total ordering across incomparable task types. How does "QLoRA training" rank against "user inference"? It depends on context: if the user is idle and the battery is full, training should win; if the user is active, inference should win. Credits encode this context-dependence naturally — agents bid more when they need the slot more urgently.

**Why 100 ms auction interval:**  
- Short enough to react to bursts (a user query arriving at tick T can win a slot at T+100 ms)
- Long enough to amortise the auction overhead (~0.2 ms for 50 agents) to < 0.2% of slot time

**Why Lua/WASM for spend policies:**  
Spend policies are per-agent configuration, not kernel logic. Lua/WASM sandboxing ensures a buggy policy cannot crash the Auctioneer or access other agents' wallets. Policies are hot-reloadable without kernel restart.

**Why Dutch auction (not Vickrey/second-price):**  
Second-price auctions require revealing the second-highest bid, which is unnecessary complexity for an internal system. Dutch (first-price) auctions are simpler, deterministic, and sufficient when all agents are trusted (same deployment boundary).

**Why anti-starvation via credit accrual (not time-slicing):**  
Time-slicing guarantees fairness but sacrifices efficiency — a background logger does not need a GPU slot every 30 ticks. Credit accrual preserves efficiency: the logger accrues credits passively and uses them only when it genuinely needs a slot (e.g., flushing a large batch).

---

## Consequences

**Positive:**
- Priority inversion eliminated: high-urgency agents always outbid low-urgency ones, regardless of static priority order
- Utilisation increases: low-priority agents fill idle capacity at near-zero credit cost
- Observable: full auction history in NATS JetStream → analytics on resource contention, cost per agent type, efficiency metrics

**Negative / Mitigations:**
- **Latency jitter in Power Save mode:** auction is suspended (ADR-025); critical tasks use fixed slots → *no jitter for safety-critical paths*
- **Credit hoarding:** a well-funded agent could accumulate credits and monopolise slots → *mitigated by daily cap (10K) and per-auction spend cap (40% of wallet)*
- **Spend policy bugs:** a policy that always bids max could starve others → *mitigated by Lua sandbox; policy is reviewed by Critic Agent before deployment*
- **100 ms overhead:** adds up to 100 ms to task start latency in worst case → *acceptable; safety-critical agents bypass the auction entirely*

---

## Alternatives Rejected

| Alternative | Reason rejected |
|-------------|----------------|
| Static priority queue | Cannot express context-dependent urgency; priority inversion at scale |
| Linux CFS (Completely Fair Scheduler) | Designed for CPU threads, not heterogeneous GPU/ANE/CPU slots; no domain-aware bidding |
| Round-robin time slicing | Fair but inefficient; allocates equally regardless of need |
| Kubernetes resource requests/limits | External dependency; does not integrate with agent wallet or safety bypass |
| Real money / cryptocurrency | Unnecessary complexity; introduces external economic incentives misaligned with system goals |

---

## Related

- ADR-025: Energy Governance — auction suspended in PowerSave; critical slots fixed
- ADR-023: (earlier draft name for this decision, retained for reference continuity)
- ADR-002: Agent-per-Resource — micro-agents representing GPU slots are the *supply* side of the market
- ADR-004: Gossip+Raft — agent registry (Gossip) tracks wallet state for anti-starvation calculation
- TDD v5.1, Parte A.3: Kernel Services — Auctioneer listed as a kernel service alongside Resource Manager
