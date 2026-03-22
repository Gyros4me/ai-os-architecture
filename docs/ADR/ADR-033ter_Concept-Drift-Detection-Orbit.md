# ADR-033ter: Concept Drift Detection in Orbit

**Status:** Proposed  
**Date:** 2026-03-03  
**Authors:** Alessandro La Gamba  
**Deciders:** Architecture Team, Infrastructure Lead  
**Extends:** ADR-033  
**Related:** ADR-032

## Context

Machine learning models in orbit face concept drift: the statistical relationship between inputs and outputs changes over time due to:

| Drift Source | Mechanism | Impact on Model |
|--------------|-----------|-----------------|
| Sensor degradation | Radiation damage to CCDs, RF front-end aging | Calibration shift, increased noise |
| Optical contamination | Micrometeorite impacts, outgassing | Point spread function change |
| Seasonal/Orbital variation | Solar angle changes, Earth albedo cycles | Illumination distribution shift |
| Target evolution | Human activity (construction, deforestation), natural disasters | Class distribution change |
| Orbital precession | Changing ground track, revisit patterns | Sampling bias |

Terrestrial drift detection relies on:
- **Ground truth labels:** Impossible in real-time for orbital observations
- **Human expert review:** 15-minute contact windows insufficient
- **Stable reference datasets:** Rapidly become stale in dynamic environment

A space-deployed AI OS must detect drift autonomously, without ground truth, and adapt training strategy to maintain model reliability.

## Decision

Implement online concept drift detection via Critic Agent ensemble divergence and distribution monitoring. Automatic mode transitions: minor drift → adaptive learning rate; major drift → SAFE mode with ground validation request.

CONCEPT DRIFT DETECTION ARCHITECTURE
─────────────────────────────────────
┌─────────────────────────────────────────────────────────────┐
│                    INPUT DATA STREAM                        │
│         (Sensor readings, inference requests, context)      │
└─────────────────────────────────────────────────────────────┘
│
┌─────────────────────┼─────────────────────┐
▼                     ▼                     ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│   Reference   │    │   Critic      │    │   Statistical │
│  Distribution │◄──►│  Ensemble     │◄──►│   Monitor     │
│   (p_ref)     │    │  (5 models)   │    │  (KL, Wasserstein)│
└───────┬───────┘    └───────┬───────┘    └───────┬───────┘
│                    │                    │
└────────────────────┼────────────────────┘
▼
┌─────────────────┐
│  Drift Detector │
│   (Decision)    │
└────────┬────────┘
│
┌──────────────┼──────────────┐
▼              ▼              ▼
┌──────────┐   ┌──────────┐   ┌──────────┐
│  No Drift │   │  Minor   │   │  Major   │
│  Continue │   │  Drift   │   │  Drift   │
│  Nominal  │   │  Adapt   │   │  SAFE    │
└──────────┘   └──────────┘   └──────────┘
plain


## Core Components

### 1. Critic Ensemble Divergence

```rust
// kernel/src/learning/drift_detector.rs

pub struct CriticEnsemble {
    models: Vec<Box<dyn CriticModel>>,  // 5 diverse architectures
    weights: Vec<f32>,                   // Dynamic weighting by recent accuracy
    
    // Diversity enforced via:
    // - Model 1: Transformer-based (Magellano base)
    // - Model 2: CNN with different receptive field
    // - Model 3: Lightweight MLP (fast, robust)
    // - Model 4: Random Forest (tree-based, different inductive bias)
    // - Model 5: Online learning (always adapting, detects stale models)
}

impl CriticEnsemble {
    /// Evaluate sample through all critics
    pub fn evaluate(&self, input: &Input, output: &Output) -> EnsembleScores {
        self.models.iter().map(|model| {
            model.score(input, output)
        }).collect()
    }
    
    /// Detect drift via inter-critic disagreement
    pub fn disagreement_drift(&self, batch: &Batch) -> DriftIndicator {
        let scores: Vec<Vec<f32>> = batch.samples.iter()
            .map(|s| self.evaluate(&s.input, &s.output))
            .collect();
        
        // Variance across critics for each sample
        let per_sample_variance: Vec<f32> = scores.iter()
            .map(|s| variance(s))
            .collect();
        
        // High variance indicates distribution shift (some models confident, others not)
        let mean_disagreement = mean(&per_sample_variance);
        
        if mean_disagreement > self.major_threshold {
            DriftIndicator::Major
        } else if mean_disagreement > self.minor_threshold {
            DriftIndicator::Minor
        } else {
            DriftIndicator::None
        }
    }
}

Intuition: If all critics agree, the input distribution matches training data. If they disagree, the sample is "unfamiliar"—indicating potential drift.
2. Distribution Distance Metrics
rust

pub struct DistributionMonitor {
    reference: OnlineDistribution,      // Running estimate of p_ref(x)
    window: SlidingWindow<Sample>,      // Recent samples (last 1000)
    metrics: DistanceMetrics,
}

impl DistributionMonitor {
    /// KL-divergence D_KL(p_ref || p_current)
    pub fn kl_divergence(&self) -> f64 {
        let p = self.reference.estimate();
        let q = self.window.distribution_estimate();
        
        p.iter().zip(q.iter())
            .map(|(p_i, q_i)| p_i * (p_i / q_i).ln())
            .sum()
    }
    
    /// Wasserstein distance (Earth Mover's Distance)
    /// More robust to outliers than KL
    pub fn wasserstein_distance(&self) -> f64 {
        let p = self.reference.cdf();
        let q = self.window.cdf();
        
        integrate(|x| (p(x) - q(x)).abs())
    }
    
    /// Combined drift score
    pub fn drift_score(&self) -> DriftScore {
        let kl = self.kl_divergence();
        let w2 = self.wasserstein_distance();
        
        // Normalize by reference distribution entropy
        DriftScore {
            magnitude: (kl + w2) / 2.0,
            confidence: self.window.confidence(),
            direction: self.gradient_direction(),  // Increasing, decreasing, oscillating
        }
    }
}

Online estimation: Use kernel density estimation (KDE) with exponential forgetting factor λ=0.99:
p_ref^(t+1)(x) = λ·p_ref^(t)(x) + (1−λ)·δ_x_t(x)
3. Drift Classification & Response
rust

pub enum DriftClassification {
    None,           // Continue nominal operation
    Minor,          // Adaptive response
    Major,          // Enter SAFE mode
    Catastrophic,   // Emergency freeze (inference-only)
}

pub struct DriftResponse {
    pub classification: DriftClassification,
    pub actions: Vec<AdaptiveAction>,
    pub telemetry: DriftReport,
}

impl DriftDetector {
    pub fn classify_and_respond(&self, score: DriftScore) -> DriftResponse {
        match score.magnitude {
            m if m < 0.1 => DriftResponse {
                classification: DriftClassification::None,
                actions: vec![AdaptiveAction::Continue],
                telemetry: self.report_nominal(),
            },
            
            m if m < 0.3 => {  // Minor drift
                let actions = vec![
                    AdaptiveAction::IncreaseLearningRate { factor: 2.0 },
                    AdaptiveAction::ShortenCheckpointInterval { to: 50 },
                    AdaptiveAction::IncreaseCriticSampling { rate: 2.0 },
                ];
                DriftResponse {
                    classification: DriftClassification::Minor,
                    actions,
                    telemetry: self.report_minor(score),
                }
            },
            
            m if m < 0.6 => {  // Major drift
                let actions = vec![
                    AdaptiveAction::EnterSafeMode,
                    AdaptiveAction::RequestGroundValidation,
                    AdaptiveAction::FreezeTraining,
                    AdaptiveAction::IncreaseTelemetryRate,
                ];
                DriftResponse {
                    classification: DriftClassification::Major,
                    actions,
                    telemetry: self.report_major(score),
                }
            },
            
            _ => {  // Catastrophic
                DriftResponse {
                    classification: DriftClassification::Catastrophic,
                    actions: vec![
                        AdaptiveAction::EmergencyFreeze,
                        AdaptiveAction::SwitchToOnnxFallback,
                        AdaptiveAction::BroadcastDistress,
                    ],
                    telemetry: self.report_catastrophic(score),
                }
            }
        }
    }
}

4. Adaptive Actions
Table

| Action                  | Trigger      | Implementation                | Recovery                                |
| ----------------------- | ------------ | ----------------------------- | --------------------------------------- |
| IncreaseLearningRate    | Minor drift  | η←2η, max 0.01                | Automatic when drift subsides           |
| ShortenCheckpoint       | Minor drift  | Every 50 steps vs 100         | Reduces rollback window                 |
| IncreaseCriticSampling  | Minor drift  | Evaluate 2× more outputs      | Faster detection of quality degradation |
| EnterSafeMode           | Major drift  | ADR-033 SAFE-QLoRA protocol   | Ground validation + manual release      |
| RequestGroundValidation | Major drift  | Priority telemetry queue      | Next contact window download            |
| FreezeTraining          | Major drift  | Halt all weight updates       | Resume post-validation                  |
| EmergencyFreeze         | Catastrophic | Inference-only, ONNX fallback | Manual mission control intervention     |

5. Reference Distribution Update
Critical challenge: the "reference" itself becomes stale if never updated.
rust

pub enum ReferenceUpdatePolicy {
    /// Never update: fixed reference from ground-trained model
    /// Risk: Gradual drift undetected (creeping normality)
    Static,
    
    /// Slow update: reference moves with exponential decay
    /// Risk: Adapts to drift, may miss slow degradation
    SlowAdapt { alpha: f64 },
    
    /// Conservative update: only update if no drift detected for N samples
    /// Balance: Adapts to legitimate evolution, flags anomalies
    Conservative { 
        min_stable_samples: usize,
        update_rate: f64,
    },
}

impl DistributionMonitor {
    pub fn maybe_update_reference(&mut self, policy: ReferenceUpdatePolicy) {
        match policy {
            ReferenceUpdatePolicy::Static => {},  // No update
            
            ReferenceUpdatePolicy::SlowAdapt { alpha } => {
                self.reference = alpha * self.reference + (1.0 - alpha) * self.window;
            },
            
            ReferenceUpdatePolicy::Conservative { min_stable_samples, update_rate } => {
                if self.stable_count > min_stable_samples && self.current_drift < 0.05 {
                    self.reference = (1.0 - update_rate) * self.reference 
                                   + update_rate * self.window;
                    self.stable_count = 0;
                }
            }
        }
    }
}

Recommendation: Conservative policy for operational missions; SlowAdapt for experimental/rapidly-evolving domains.
Rationale
Why ensemble disagreement vs. statistical tests only?
Statistical tests (KL, Wasserstein) detect distribution shift but not semantic drift (same distribution, different labels). Critic ensemble detects when model predictions become unreliable—even if input statistics appear normal.
Why 5 critics?
Empirical sweet spot: odd number enables majority voting; 5 provides diversity without excessive compute (20% overhead vs. single critic). Architectures span transformer, CNN, MLP, tree, online to maximize disagreement sensitivity.
Why not use ground truth for validation?
Orbital operations often lack real-time labels (e.g., anomaly detection: true anomaly confirmed only after investigation). Self-supervised disagreement provides immediate signal without ground delay.
Why major drift → SAFE mode vs. automatic adaptation?
Major drift may indicate sensor failure, adversarial attack, or mission-critical environmental change. Automatic adaptation risks learning incorrect patterns. Human-in-the-loop (via ground contact) ensures mission safety.
Why catastrophic → ONNX fallback?
Magellano weights may be corrupted or poisoned. ONNX static model (frozen at launch) provides trusted baseline for emergency operations while preserving inference capability.
Consequences
Positive
Autonomous reliability: Detects degradation without ground intervention; maintains model accuracy over multi-year missions
Graduated response: Minor drift adapts automatically; major drift preserves safety; catastrophic preserves mission
Telemetry optimization: Drift reports prioritize anomalous periods for ground analysis, maximizing science return from limited bandwidth
Root cause analysis: Disagreement patterns identify drift type (sensor vs. target vs. environmental)
Negative / Mitigations
Table

| Issue                                                                      | Mitigation                                                                                                           |
| -------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| False positive rate: Natural variability may trigger minor drift alerts    | Conservative thresholds (0.1, 0.3, 0.6) tuned on historical data; hysteresis in state transitions                    |
| Ensemble computational cost: 5× Critic evaluation                          | Lightweight critics (Models 3-5 are <10M parameters); evaluate on subset (10% of inferences); ANE parallel execution |
| Reference staleness: Conservative update may miss slow drift               | Annual ground-commanded reference reset; cross-validation with constellation peers (federated drift detection)       |
| Catastrophic freeze availability: Emergency mode may trigger unnecessarily | Two-phase confirmation: ensemble disagreement + statistical test must both trigger; manual override via ADR-026      |

Integration with ADR-033
ADR-033ter extends ADR-033 state machine with drift-aware transitions:
plain

ADR-033 State Machine (enhanced):
┌─────────────┐     drift: minor     ┌─────────────┐
│  STANDALONE │─────────────────────►│  STANDALONE │
│  (nominal)  │◄─────────────────────│  (adaptive) │
└──────┬──────┘     drift: resolved   └──────┬──────┘
       │                                      │
       │ drift: major                         │ drift: major
       ▼                                      ▼
┌─────────────┐                          ┌─────────────┐
│    SAFE     │◄────────────────────────►│    SAFE     │
│   (frozen)  │   ground: validate       │  (adaptive  │
│             │   ground: resume         │   pending)  │
└─────────────┘                          └─────────────┘
       ▲
       │ drift: catastrophic
       │
┌─────────────┐
│  EMERGENCY  │
│ (ONNX only) │
└─────────────┘

Federated Drift Detection: Constellation nodes share drift scores (not raw data) via ADR-033 FEDERATED-QLoRA. Global drift pattern indicates environmental change (solar event); isolated drift indicates node-specific sensor failure.
Related
ADR-007: Circuit Breaker — graceful degradation patterns
ADR-025: Energy Governance — drift detection runs in PowerSave mode
ADR-026: Human Override — emergency freeze can be manually triggered
ADR-032: Quantum-Assisted Search — quantum kernel Critic for ensemble diversity
ADR-033: Space-Grade Self-Learning — base state machine extended here
ADR-033bis: Federated Privacy — secure sharing of drift scores
TDD Reference
TDD v5.1: Base terrestrial architecture
TDD v5.2 Space Computing Extension, Part S4.6: Concept Drift Detection integration



