# ADR-033: Space-Grade Self-Learning Improvement

**Status:** Proposed  
**Date:** 2026-03-03  
**Authors:** Alessandro La Gamba  
**Deciders:** Architecture Team, Infrastructure Lead  
**Extends:** ADR-008, ADR-025, ADR-027, ADR-030, ADR-031

## Context

The terrestrial QLoRA nightly feedback loop (ADR-008) assumes four conditions that are systematically violated in orbital environments:

| Terrestrial Assumption | Space Reality | Consequence of Violation |
|------------------------|---------------|-------------------------|
| Stable 200W+ power | 50-200W with 45-minute eclipse cycles (LEO) | Training interruption, model corruption |
| ECC DRAM with negligible bit-flips | 1-200 SEU/day/MB from cosmic radiation | Silent weight corruption, inference divergence |
| Ground station sync every cycle | 0-15 minute contact window every 90 minutes (LEO) | Gradient staleness, convergence failure |
| Fixed training clock | Thermal cycling ±300°C causes clock drift | Distributed training desynchronization |
| Single-node training | N-node constellation with partial data overlap | Data silos, suboptimal global model |

A space-deployed AI OS must learn continuously and autonomously without ground intervention, survive radiation-induced memory corruption, and improve through federation across intermittently-connected nodes.

## Decision

Replace monolithic nightly QLoRA with three-mode space-adaptive variant: **AUTONOMOUS** (eclipse-aware micro-epochs + SEU scrubbing), **SAFE** (radiation storm freeze+audit+rollback), **FEDERATED** (DTN-based FedAvg with ZK-SLA gradient proofs). Implement SEU guard: CRC32 per 64-weight block, 10s scrub cycle, NVM checkpoint chain.

┌─────────────────────────────────────────────────────────────────┐
│           SPACE QLoRA STATE MACHINE (L3 Extension)              │
│                                                                 │
│    ┌─────────────┐         uplink loss         ┌─────────────┐ │
│    │  STANDALONE │◄───────────────────────────►│   DISASTER  │ │
│    │   (Mode 1)  │                             │  RECOVERY   │ │
│    │ AUTONOMOUS  │    constellation join       │   (Mode 2)  │ │
│    │   QLoRA     │◄───────────────────────────►│  SAFE-QLoRA │ │
│    └──────┬──────┘                             └──────┬──────┘ │
│           │                                           │         │
│           └──────────────────┬────────────────────────┘         │
│                              │                                  │
│                              ▼                                  │
│                    ┌─────────────────┐                          │
│                    │  CONSTELLATION  │                          │
│                    │     MESH        │                          │
│                    │   (Mode 3)      │                          │
│                    │ FEDERATED-QLoRA │                          │
│                    └─────────────────┘                          │
│                                                                 │
│  Transitions: automatic via EnvironmentAgent (solar, SEU, link) │
└─────────────────────────────────────────────────────────────────┘
plain


**Privacy Extension:** See ADR-033bis for Secure Multi-Party Computation (SMPC) with pairwise masking.  
**Drift Detection Extension:** See ADR-033ter for online concept drift detection via Critic ensemble.

## Core Components

### 1. SEU-Resilient Weight Architecture

```rust
// kernel/src/learning/seu_guard.rs

pub struct SeuGuard {
    weights: Vec<f16>,                    // Active model weights
    crc_blocks: Vec<u32>,                 // CRC32 per 64-weight block (0.5% overhead)
    seu_counter: AtomicU64,               // Telemetry: total SEU events detected
    nvm_checkpoint: MRAMWriter,           // Magnetic RAM (rad-hard, non-volatile)
    last_checkpoint_orbit: OrbitTime,     // For incremental checkpointing
}

impl SeuGuard {
    /// Background scrub — called every 10s by ScrubAgent
    pub fn scrub(&mut self) -> ScrubReport {
        let mut flipped = 0usize;
        
        for (block_idx, chunk) in self.weights.chunks_mut(64).enumerate() {
            let computed = crc32(chunk);
            
            if computed != self.crc_blocks[block_idx] {
                // SEU detected: rollback this block from NVM checkpoint
                self.restore_block_from_nvm(block_idx);
                flipped += 1;
                self.seu_counter.fetch_add(1, Ordering::Relaxed);
                
                // Telemetry for ground analysis of radiation environment
                self.emit_seu_event(SeuEvent {
                    block_idx,
                    expected_crc: self.crc_blocks[block_idx],
                    actual_crc: computed,
                    orbit_position: current_orbit_position(),
                    solar_activity: get_space_weather_index(),
                });
            }
        }
        
        // Periodic full checkpoint every 100 steps or 5 minutes
        if self.steps_since_checkpoint > 100 {
            self.full_checkpoint_to_mram();
        }
        
        ScrubReport {
            blocks_checked: self.crc_blocks.len(),
            blocks_restored: flipped,
            timestamp: orbit_time_now(),
            next_scrub: orbit_time_now() + Duration::seconds(10),
        }
    }
    
    /// Restore single corrupted block without full rollback
    fn restore_block_from_nvm(&mut self, block_idx: usize) {
        let nvm_addr = self.nvm_checkpoint.base_addr + block_idx * 64 * size_of::<f16>();
        let restored = self.nvm_checkpoint.read_block(nvm_addr);
        self.weights[block_idx * 64..(block_idx + 1) * 64].copy_from_slice(&restored);
        self.crc_blocks[block_idx] = crc32(&restored);
    }
}

2. Mode 1: AUTONOMOUS-QLoRA
Operational: Single satellite, no ground contact, sunlit/eclipse cycles.
Orbit-Cycle Training Schedule (90-minute LEO):
plain

T+00 min  [SUNLIT — ACTIVE]
├── Magellano inference: nominal operation
├── Feedback Buffer: accumulate (prompt, output, critic_score) tuples
│   └── Critic Agent evaluates quality; score < 0.85 triggers regeneration
├── CRC Scrubber: background weight integrity check (10s cycle)
└── Memory Agent: RAG vector store updates

T+44 min  [PRE-ECLIPSE CHECKPOINT]
├── Trigger: SolarPowerAgent detects eclipse -5min via orbit propagation
├── Action: serialize LoRA adapter + optimizer state to MRAM
│   ├── Format: SpaceCheckpoint {
│   │   weights_crc32: [u32; 1024],      // Per-block CRCs
│   │   optimizer_state: AdamState,      // Moments, learning rate
│   │   orbit_id: u32,                   // For traceability
│   │   epoch: u16,
│   │   timestamp: OrbitTime,
│   │   solar_activity_index: f32,       // Context for ground analysis
│   │ }
│   └── Size: ~400MB (delta-only, rank-16 adapter)
└── Time budget: <30s to complete before power drops

T+45 min  [ECLIPSE — POWER-CONSTRAINED TRAINING]
├── Available power: 15-40W (battery, no solar)
├── Training mode: MICRO-EPOCH (1/4 of nominal epoch)
│   ├── Batch size: 2 (vs terrestrial 8)
│   ├── Gradient clipping: 0.5 (tighter than terrestrial 1.0)
│   ├── Learning rate: 0.5× nominal (conservative)
│   └── Max steps: 25 (vs 100 nominal)
├── SEU guard: re-verify CRC after each batch; rollback on mismatch
└── Thermal management: pause if chip temp >85°C

T+90 min  [ECLIPSE EXIT — RESUME]
├── Verify checkpoint integrity via CRC chain
├── If SEU detected during eclipse: resume from T+44 checkpoint
├── Else: continue from current state
├── Emit: ModelVersionManifest (ADR-027) with orbit_id tag
└── Telemetry queue: compact report for next ground pass

T+92 min  [CONTACT WINDOW — IF AVAILABLE]
├── Upload: delta adapter (compressed, ~50MB)
│   └── Compression: quantization NF4 + entropy coding
├── Download: ground-side gradient updates (optional, if available)
│   └── Validation: ZK-proof of ground training integrity
└── Protocol: DTN Bundle Protocol (RFC 5050), store-and-forward
    └── Bundle custody transfer for reliability


Energy-Aware Training Scheduler:
rust

pub struct EclipseAwareScheduler {
    orbit_propagator: SGP4,  // Simplified General Perturbations #4
    power_budget: PowerProfile,
    training_queue: Vec<TrainingTask>,
}

impl TrainingScheduler for EclipseAwareScheduler {
    fn schedule(&self, tasks: Vec<TrainingTask>) -> Schedule {
        let next_eclipse = self.orbit_propagator.next_eclipse();
        let available_energy = self.power_budget.solar_forecast(next_eclipse);
        
        // Prioritize tasks by Critic score improvement potential
        // Schedule high-intensity training before eclipse
        // Reserve MICRO-EPOCH for eclipse period
        
        Schedule::new(tasks, available_energy, next_eclipse)
    }
}

3. Mode 2: SAFE-QLoRA (Disaster Recovery)
Trigger Conditions:
Uplink silence >3 contact windows (270 minutes LEO / 72 hours deep space)
SEU rate >10 events/hour (radiation storm, solar proton event)
Power <20% battery (eclipse anomaly, battery degradation)
Gossip: peer declares this node SUSPECTED (ADR-030)
State Machine:

| Phase                  | Time          | Actions                                                                                                                                                                              | Verification            |
| ---------------------- | ------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------- |
| **FREEZE**             | T+0s          | Halt all QLoRA training immediately; flush feedback buffer to NVM (<5s); broadcast FIPA-ACL INFORM(status=SAFE\_MODE, orbit\_id)                                                     | KernelSupervisor ACK    |
| **INTEGRITY AUDIT**    | T+5s          | Full CRC scan of all weight blocks (3.3B model = 6.6GB weights @ 100MB/s = 66s); compare against NVM checkpoint manifest; emit ZK-proof of audit result (ADR-013)                    | Groth16 proof           |
| **SELECTIVE ROLLBACK** | T+2min        | Corrupt blocks >5%: full rollback to N-1 checkpoint; corrupt blocks 1-5%: selective restore + re-CRC; corrupt <1%: inline correction                                                 | 100% CRC pass           |
| **DEGRADED INFERENCE** | T+5min        | Magellano: inference ONLY (no weight updates); ONNX static model fallback if Magellano integrity <95%; diagnostic telemetry every 60s                                                | Critic score monitoring |
| **RECOVERY**           | Link restored | Upload audit report + SEU event log (compressed, ~340KB for 2,847 events); download validated ground checkpoint if drift >threshold; gradual re-enable: Critic → Training → Full ops | Ground validation ACK   |

Recovery KPIs:
Freeze-to-safe-inference: <5 minutes
Full integrity audit (3.3B model): <2 minutes
Rollback and re-verify: <10 minutes
Full operational recovery: <30 minutes after link restore
4. Mode 3: FEDERATED-QLoRA
Operational: Multiple constellation nodes with intermittent connectivity.
Federated Round Structure (90-minute LEO orbit / 24-hour deep space):
plain

Phase A: LOCAL TRAINING [T+0..75% of orbit period]
├── Each node runs AUTONOMOUS-QLoRA on local sensor/task data
│   └── Data never leaves node (privacy by construction)
├── Produces: local gradient G_i (LoRA adapter delta, ~35MB)
├── Signs: ZK-proof of training integrity {
│   pub_inputs: {node_id, round_id, num_samples, final_loss},
│   priv_inputs: {raw_data, intermediate_gradients},  // Never transmitted
│   proof: Groth16 192-byte proof
│ }
└── Reputation update: +0.01 for successful proof submission

Phase B: GOSSIP BROADCAST [T+75%..80%]
├── Node broadcasts: {SHA256(G_i), node_id, round_id, zk_proof_hash}
│   └── Via SWIM gossip over Bus-4 (DTN bundles for deep space)
├── Convergence: O(log N) rounds
│   └── ~30s for 10-node LEO, ~2 hours for 5-node deep space
└── Anti-entropy: nodes compare round_ids, request missing gradients

Phase C: GRADIENT AGGREGATION [T+80%..85%]
├── Elected aggregator: Raft leader (highest reputation × uptime)
│   └── Rotates every round for fairness
├── Collects: G_1..G_n via DTN bundle (already in-flight since T+70%)
├── Aggregation: FedAvg with reputation weighting
│   G_agg = Σ(reputation_i × G_i) / Σ reputation_i
│   where reputation_i ∈ [0,1] from ADR-030 ZK-SLA outcomes
├── Privacy: Differential Privacy noise (ε=1.0, δ=1e-5)
│   └── Gaussian noise scaled to gradient L2 norm
└── ZK-SLA: Aggregator proves correct weighted average
    WITHOUT revealing individual G_i (privacy preserved)

Phase D: HOT-SWAP DEPLOYMENT [T+85%..90%]
├── Raft consensus on G_agg (2/3 quorum for Byzantine fault tolerance)
├── Broadcast: new adapter manifest (ADR-027) with version hash
├── Each node: merge G_agg into local Magellano
│   └── Hot-swap: <3s atomic pointer swap, no inference interruption
└── Rollback trigger: if Critic score drops >5%, revert to local G_i
    └── Automatic, no ground intervention required


Deep-Space Adaptation (DTN Bundle Protocol):
Standard TCP/IP fails at 3-22 minute one-way delays
Bundle Protocol (RFC 5050) with custody transfer ensures reliability
Gradient sparsification: top-1% weights only → 500KB vs 50MB
At 8Kbps X-band: 500KB transfer = 8 minutes (acceptable for 24-hour round)
rust

// Bundle Protocol integration
pub struct FederatedBundle {
    header: BundleHeader,           // Source, destination, timestamp
    payload: GradientPayload,       // CKKS-encrypted + compressed
    extension: ZkProofExtension,    // 192-byte Groth16 proof
    custody: CustodyBlock,          // Acknowledgment chain
}

impl DelayTolerant for FederatedBundle {
    fn transmit(&self, link: &mut DtnLink) -> TransmissionResult {
        // Store-and-forward: bundle held until next contact window
        // Custody transfer: intermediate nodes guarantee delivery
        // Reactive fragmentation: split for link MTU, reassemble at dest
        link.custody_transfer(self)
    }
}

5. Quantum-Enhanced Learning (ADR-032 Integration)
VQE Hyperparameter Optimization:
Explore QLoRA hyperparameter landscape (learning rate, rank, alpha)
Multi-objective: minimize energy (training cost), maximize improvement
Simulated: PennyLane VQE, 10-20 evaluations vs 50-100 classical grid search
Result: 30-minute optimized cycle vs 60-minute solar-gated classical
Quantum Kernel Critic:
5-dimension quality evaluation (accuracy, latency, power, safety, novelty)
Quantum kernels capture non-linear correlations inadequate for classical SVM
Simulated: matrix operations on Magellano, cached in Knowledge Graph
Rationale
Why three modes instead of adaptive parameters?
A unified algorithm with dynamic parameters would be simpler but fails to provide deterministic behavior certification required for space missions. Regulatory bodies (ESA, NASA) require explicit mode definitions with guaranteed behavior bounds. SAFE mode, for example, must provably halt all training within 5 seconds—achievable only with a dedicated state machine, not parameter tuning.
Why CRC32 vs. stronger hash (SHA-256)?
CRC32 is sufficient for error detection (not cryptographic integrity) and can be computed in 1 CPU cycle per byte on modern processors. SHA-256 would add 10× overhead with no benefit for SEU detection (random bit-flips, not adversarial attacks). ADR-011 SIMD Merkle provides cryptographic integrity at the bundle level.
Why MRAM for checkpointing?
Magnetic RAM is immune to radiation-induced bit-flips (no charge storage), non-volatile (survives power loss), and has unlimited write endurance (vs. flash wear-out). The trade-off is density (MRAM is 4× larger than DRAM per bit), acceptable for 400MB checkpoints vs. 6.6GB active weights.
Why FedAvg with reputation vs. FedProx or SCAFFOLD?
FedProx handles heterogeneous data distributions but requires a central server. SCAFFOLD corrects client drift but doubles communication cost. FedAvg with reputation weighting (from ADR-030 ZK-SLA outcomes) achieves similar robustness with minimal overhead and full decentralization.
Why differential privacy in federation?
Even encrypted gradients can leak training data membership (membership inference attacks). Differential privacy provides mathematical guarantee: ε=1.0 means any single data point changes output probability by at most e^1.0 ≈ 2.7×, preventing reconstruction of sensitive orbital observations.

# Consequences
Positive
Zero model corruption: CRC scrubbing + NVM checkpointing ensures >99.9% weight integrity in LEO SEU environment
Autonomous learning: No ground contact required for continuous improvement; Critic Agent is sole quality gate
Privacy-preserving federation: No raw data leaves nodes; ZK-proofs verify correct aggregation
Fast disaster recovery: <5 minute freeze-to-safe-inference vs. hours for ground intervention
Quantum-enhanced: VQE optimization reduces training time 50%; quantum kernels improve Critic accuracy
Negative / Mitigations
Table

| Issue                                                                                       | Mitigation                                                                                                                                      |
| ------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| Training throughput reduced 75% in eclipse: Batch size 2 vs 8, 1/4 epochs                   | Eclipse training is "consolidation" of sunlit learning; sunlit periods use full batch size; net improvement still positive                      |
| Federated round overhead: 60-120s per 90-min orbit (11-22% overhead)                        | Overlap communication with computation (gradient pre-fetching); deep space rounds are 24-hour, making overhead negligible                       |
| NVM checkpoint storage: 400MB per checkpoint × 100 checkpoints = 40GB                       | Circular buffer, retain only last 10 checkpoints + 1 golden reference; MRAM density improving 2× per year                                       |
| DTN integration complexity: Requires ION (Interplanetary Overlay Network) or Rust-BP daemon | Bus-4 abstraction hides complexity; application code unchanged; fallback to direct link for LEO                                                 |
| DP noise reduces model accuracy: ε=1.0 typically costs <2% accuracy                         | Adaptive epsilon: lower (stricter privacy) for sensitive data, higher for public datasets; reputation-weighted aggregation reduces noise impact |

Rollout Phases
Table

| Phase                  | Timeline        | Deliverables                                                                                                  | Hardware                  | Milestone                 |
| ---------------------- | --------------- | ------------------------------------------------------------------------------------------------------------- | ------------------------- | ------------------------- |
| 0: Simulation          | Q2-Q4 2026      | SEU fault injection framework; 3-mode state machine; AUTONOMOUS-QLoRA on M4 Max; SAFE mode trigger testing    | Apple M4 Max              | Single-node validation    |
| 1: LEO Prototype       | Q4 2026-Q2 2027 | MRAM checkpoint driver; DTN Bundle Protocol; 2-node FEDERATED-QLoRA; ZK-proof gradient verification           | ARM Cortex-R52 + MRAM     | Ground constellation test |
| 2: CubeSat Validation  | Q3 2027-Q2 2028 | 3U/6U deployment; real SEU environment; full mode transitions; 6-month autonomous operation                   | Custom SoC + MRAM         | Space qualification       |
| 3: Constellation Scale | 2028-2030       | 10+ node federation; quantum-enhanced VQE; inter-satellite gradient offloading; deep space (GEO) validation   | Flight-qualified hardware | Operational constellation |
| 4: Deep Space          | 2030+           | 24-hour federated rounds; multi-year autonomous learning; fault-tolerant quantum Critic; Jupiter mission prep | Rad-hard QPU + MRAM       | Interplanetary ready      |

Alternatives Rejected
Table

| Alternative                                 | Reason Rejected                                                                                                |
| ------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| Terrestrial QLoRA unchanged                 | Fails on SEU: silent weight corruption leads to inference divergence; no eclipse awareness causes power faults |
| Training ground-side only                   | Insufficient contact windows (8-15 min/90 min LEO); violates ADR-030 sovereignty; 22-minute latency deep space |
| Full training freeze in orbit               | Zero learning for multi-year missions; model drift from concept change (sensor degradation, orbital evolution) |
| Standard federated learning (PySyft/Flower) | No SEU resilience; requires stable TCP/IP; no ZK verification; Python runtime incompatible with Rust kernel    |
| Blockchain-based model updates              | 12-15s latency incompatible with real-time hot-swap; energy consumption; no SEU protection                     |
| Centralized constellation coordinator       | SPOF violates ADR-030; ground dependency; single node compromise affects entire constellation                  |

Related
ADR-004: Gossip+Raft — membership and consensus for FEDERATED mode
ADR-007: Circuit Breaker — graceful degradation patterns reused in SAFE mode
ADR-008: QLoRA Base — terrestrial foundation extended by this ADR
ADR-011: SIMD Merkle — cryptographic integrity for gradient bundles
ADR-013: ZK Execution Proofs — verification of training and aggregation correctness
ADR-025: Energy Governance — solar-aware scheduling for eclipse transitions
ADR-026: Human Override — propagates to all modes via Bus-4
ADR-027: Semantic Agent Versioning — adapter manifest exchange in federation
ADR-030: Federated Constellation Governance — reputation system and ZK-SLA framework
ADR-031: Quantum-Assisted Search — VQE optimization and quantum kernel Critic
ADR-033bis: Federated Learning Privacy Bounds — SMPC with pairwise masking (extends this ADR)
ADR-033ter: Concept Drift Detection in Orbit — online drift via Critic ensemble (extends this ADR)
TDD Reference
TDD v5.1: Base terrestrial architecture
TDD v5.2 Space Computing Extension, Part S4: Space-Grade Self-Learning integration



