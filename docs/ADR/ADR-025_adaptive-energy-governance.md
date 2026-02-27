# ADR-025: Adaptive Energy Governance

**Status:** Proposed  
**Date:** 2026-02-26  
**Authors:** Alessandro La Gamba  
**Deciders:** Architecture team  

---

## Context

0xMeridian runs on a heterogeneous device fleet spanning battery-constrained edge devices (iPhone, iPad, wearables, drones, IoT sensors) and always-on servers (Mac Studio, cloud instances). A uniform power behaviour would drain edge batteries in minutes and cause thermal throttling on high-density inference workloads.

The kernel must adapt dynamically to:
- Real-time battery state (percentage, charge rate, temperature)
- Power source type (AC mains, USB-C PD, wireless, battery-only)
- Thermal envelope (CPU/GPU junction temperature thresholds)
- Task criticality (safety-critical tasks must never be degraded)

No existing OS-level energy management integrates inference engine modulation, QLoRA scheduling, and agent prioritisation into a single coherent policy.

---

## Decision

**Implement an Energy Governor in the Rust Kernel that dynamically modulates Magellano's quantisation level, the QLoRA nightly cycle, and the agent scheduler's work-stealing depth based on a three-tier Power Profile.**

```rust
// kernel/src/power/governor.rs

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum PowerProfile {
    Performance, // Plugged in OR battery > 80%
    Balanced,    // Battery 20–80%, not charging
    PowerSave,   // Battery < 20%, not charging
}

pub struct PowerGovernor {
    profile:      PowerProfile,
    last_battery: f32,
    last_temp_c:  f32,
}

impl PowerGovernor {
    /// Called every 5 s by the kernel heartbeat tick.
    pub fn adjust_profile(&mut self, battery_pct: f32, is_charging: bool, temp_c: f32) {
        let new_profile = match (battery_pct, is_charging, temp_c) {
            (_, true, t) if t < 85.0  => PowerProfile::Performance,
            (p, _, t)    if p > 80.0 && t < 80.0 => PowerProfile::Performance,
            (p, _, _)    if p > 20.0 => PowerProfile::Balanced,
            _                        => PowerProfile::PowerSave,
        };

        if new_profile != self.profile {
            self.profile = new_profile;
            // Publish profile-change event on Bus 2 (NATS)
            self.publish_profile_change(new_profile);
        }
    }

    fn publish_profile_change(&self, profile: PowerProfile) {
        // Subscribers: Magellano HAL, QLoRA Scheduler, Agent Scheduler
        nats::publish("aios.kernel.power.profile", &profile.to_json());
    }
}
```

### Three-Tier Power Profile

| Profile | Trigger | Magellano Model | QLoRA Loop | Agent Scheduler | Auction Budget (ADR-023) |
|---------|---------|-----------------|-----------|-----------------|--------------------------|
| **Performance** | Plugged in OR battery ≥ 80% AND temp < 85°C | Magellano 3.3B NF4 (full quality) | Active — nightly scheduled | All agents active, aggressive GPU bidding | No cap on credit spend |
| **Balanced** | Battery 20–80%, not charging | Magellano 3.3B NF4 (default) | Active only if battery > 50% | Non-critical agents throttled to 50% tick rate | Credit spend capped at 60% of baseline |
| **Power Save** | Battery < 20% OR temp ≥ 85°C | Magellano 77M Q8 (minimal) | Disabled — resumable on next charge | Only safety-critical agents active | Auction suspended; critical tasks use fixed slots |

### Magellano Integration

```swift
// magellano/Sources/MagellanoPowerAdapter.swift

class MagellanoPowerAdapter: NATSSubscriber {
    override func onMessage(_ topic: String, _ payload: Data) {
        guard topic == "aios.kernel.power.profile" else { return }
        let profile = PowerProfile(from: payload)

        switch profile {
        case .performance:
            ModelLoader.shared.loadModel(.magellano3B_NF4)
        case .balanced:
            ModelLoader.shared.loadModel(.magellano3B_NF4)   // same, but ANE budget halved
            ANEBudget.shared.setLimit(.half)
        case .powerSave:
            ModelLoader.shared.loadModel(.magellano77M_Q8)
            ANEBudget.shared.setLimit(.minimal)
        }
    }
}
```

---

## Rationale

**Why three tiers and not continuous adjustment:**  
Continuous hysteresis tuning introduces latency variability that is unacceptable for real-time tasks (haptic feedback, safety alerts). Three discrete, well-defined profiles let every component cache its configuration and avoid constant re-negotiation.

**Why kernel-level (not application-level) governance:**  
Application-level power management is overridden by user code. A kernel-level governor enforces the policy transparently — an agent cannot opt out of Power Save if the battery is at 15%.

**Why the battery threshold is 20% (not 30% or 10%):**  
- At < 20%, most mobile OS kernels begin aggressive background kill — aligning with this threshold avoids conflicts with the host OS.  
- 20% provides ~25–40 min of residual autonomy on most devices, enough to complete in-flight safety-critical tasks before shutdown.

**Why QLoRA is disabled in Power Save:**  
Training runs consume 4–6× the power of inference. Running QLoRA at 15% battery would shorten the session by ~40 min while providing zero user-facing benefit (the improved adapter would only be used in the next session, after a recharge).

**Why Magellano 77M Q8 in Power Save (not llama.cpp GGUF):**  
77M runs entirely on CPU with negligible ANE usage. llama.cpp GGUF Q4 at context lengths > 512 tokens would consume more power than 77M Q8 due to higher memory bandwidth. The 77M model is purpose-built for intent parsing, formatting, and trivial responses — exactly the workload that matters on a low-battery device.

---

## Consequences

**Positive:**
- Battery life extended significantly: ~6 h continuous surgical assist vs ~3 h without Power Save
- Thermal throttling prevented proactively rather than reactively
- Green AI: inference carbon footprint reduced ~40% over a full charge cycle in mixed use
- Transparent to agents: the profile change is a single NATS event; no agent code changes required

**Negative / Mitigations:**
- **Latency variability:** Power Save increases response latency from ~80 ms (3.3B Metal) to ~300 ms (77M CPU) → *mitigated by pre-announcing profile change on Bus 2 so the Interface Agent can update its SLA timer*
- **Non-deterministic for real-time systems:** Power profile can change mid-task → *mitigated by pinning safety-critical agents to Performance-equivalent slots regardless of profile (capability flag `REQUIRES_PERFORMANCE_SLOT`)*
- **Model swap latency:** Switching from 3.3B to 77M takes ~800 ms during the profile transition → *mitigated by pre-loading 77M into standby RAM when battery crosses 30% (anticipatory load)*

---

## Alternatives Rejected

| Alternative | Reason rejected |
|-------------|----------------|
| macOS/iOS NSProcessInfo power state only | Too coarse (2 states: low power / normal); does not expose per-component control |
| Agent-level power management | Inconsistent; individual agents have no global visibility; impossible to enforce system-wide |
| Fixed quantisation (always 3.3B or always 77M) | Either wastes battery or wastes quality; no adaptation to real conditions |
| Continuous frequency scaling | Adds latency jitter unacceptable for safety-critical workflows; complicates SLA guarantees |

---

## Related

- ADR-003: Magellano HAL — defines the `ModelLoader` API that Power Save switches backends through
- ADR-023: Internal Compute Market — auction is suspended in Power Save; critical tasks use fixed allocation
- ADR-007: Circuit Breaker — `PowerSave` mode implicitly activates safe-mode for non-critical agents
- ADR-008: QLoRA Loop — Power Governor gates the nightly training cycle
- TDD v5.1, Parte A.3: Kernel Services — Power Governor listed as a kernel service alongside Resource Manager and Task Scheduler

---

## Responding to "Why not just let the OS handle power management?"

The host OS (macOS, iOS, Linux) manages hardware power states (CPU frequency, display brightness). It does not know that:
1. Running Magellano 3.3B at 15% battery will terminate the session before a surgical procedure completes
2. The QLoRA training job running in the background is non-critical and should yield to the user session
3. A specific agent has a `REQUIRES_PERFORMANCE_SLOT` flag that must never be degraded

The Energy Governor is an *application-domain* power policy layered on top of the OS power policy — they are complementary, not redundant.
