# ADR-008: QLoRA with Feedback Loop for Continuous Training

**Status:** Accepted  
**Date:** 2026-02-17  
**Authors:** Alessandro La Gamba  
**Deciders:** Architecture team  

---

## Context

Static model deployments require manual retraining, versioning, and redeployment cycles to incorporate new knowledge. The AI OS operates in dynamic environments (edge devices, user-specific workflows, evolving domains) where a model that cannot adapt quickly becomes obsolete.

The challenge: full fine-tuning of Magellano 3.3B requires significant GPU memory and hours of compute — prohibitive for nightly cycles on edge Apple Silicon hardware. We need a method that:

1. **Trains only on errors and improvements** observed during the day's operation
2. **Has minimal memory footprint** — 16GB Unified Memory must support inference + training simultaneously
3. **Deploys without downtime** — the OS cannot be paused for model updates
4. **Is reversible** — if the new adapter degrades quality, automatic rollback

Four approaches were evaluated:
- **Option A:** Full fine-tuning nightly (impractical at the edge)
- **Option B:** LoRA without quantization (lower memory but still 3–4GB VRAM)
- **Option C:** QLoRA (4-bit quantized base model + LoRA adapters)
- **Option D:** RLHF full pipeline (too complex, requires reward model training)

---

## Decision

**QLoRA (Quantized Low-Rank Adaptation) with rank=16, alpha=32, NF4 4-bit quantization, targeting 7 key modules. Nightly training cycle fed by Critic Agent feedback. A/B gate (≥5% improvement) gates deployment. Hot-swap with zero downtime.**

```
╔══════════════════════════════════════════════════════════════════╗
║              NIGHTLY QLORA SELF-IMPROVEMENT LOOP                ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  During Day (continuous)                                         ║
║  ┌──────────┐  critique  ┌───────────┐  write   ┌────────────┐  ║
║  │  Agents  │──────────►│   Critic  │─────────►│  Feedback  │  ║
║  │ (any tier)│          │  Agent    │          │  Buffer    │  ║
║  └──────────┘           └───────────┘          │  (NATS JS) │  ║
║                                                └────────────┘  ║
║                                                      │          ║
║  At Night (scheduled 02:00 local)                    │          ║
║       ┌──────────────────────────────────────────────┘          ║
║       ▼                                                          ║
║  ┌─────────────┐  prepare  ┌─────────────┐  train  ┌─────────┐ ║
║  │  Feedback   │─────────►│   Dataset   │────────►│  QLoRA  │ ║
║  │  Collector  │          │   Builder   │         │ Trainer │ ║
║  │  (Haskell)  │          │  (Haskell)  │         │(Py/Swift│ ║
║  └─────────────┘          └─────────────┘         └────┬────┘ ║
║                                                         │       ║
║                              ┌──────────────────────────┘       ║
║                              ▼                                   ║
║                       ┌─────────────┐                            ║
║                       │   A/B Gate  │ ── fail (< +5%) ──►  skip ║
║                       │  (Critic)   │                            ║
║                       └──────┬──────┘                            ║
║                              │ pass (≥ +5%)                      ║
║                              ▼                                   ║
║                       ┌─────────────┐                            ║
║                       │  Hot-Swap   │ drain v1 → load v2 → done ║
║                       │  (<2.3s)    │                            ║
║                       └─────────────┘                            ║
╚══════════════════════════════════════════════════════════════════╝
```

### QLoRA Configuration

```python
qlora_config = {
    # LoRA parameters
    "r":              16,          # rank — balance between expressiveness and memory
    "lora_alpha":     32,          # scaling factor (alpha/r = 2.0)
    "lora_dropout":   0.05,
    "target_modules": [            # 7 modules — key attention + MLP projections
        "q_proj", "k_proj", "v_proj", "o_proj",
        "gate_proj", "up_proj", "down_proj"
    ],
    "bias":           "none",

    # Quantization (NF4 = Normal Float 4-bit)
    "load_in_4bit":           True,
    "bnb_4bit_quant_type":    "nf4",
    "bnb_4bit_use_double_quant": True,  # nested quantization for quant constants
    "bnb_4bit_compute_dtype":  torch.bfloat16,

    # Training
    "num_train_epochs":       3,
    "learning_rate":          2e-4,
    "gradient_checkpointing": True,    # -60% VRAM at cost of ~20% speed
    "per_device_train_batch_size": 4,
    "gradient_accumulation_steps":  4, # effective batch = 16
    "warmup_ratio":           0.03,
    "lr_scheduler_type":      "cosine",
    "fp16":                   False,
    "bf16":                   True,    # bfloat16 on Apple Silicon ANE
}
```

### Memory Budget (M2 Ultra, 16GB Unified)

| Component | VRAM Usage |
|-----------|-----------|
| Base model (NF4 quantized) | 1.7 GB |
| LoRA adapters (rank=16) | ~35 MB |
| Activations (gradient checkpointing ON) | ~2.0 GB |
| Optimizer states (AdamW 8-bit) | ~0.5 GB |
| **Total training** | **~4.3 GB** |
| Inference (concurrent) | ~2.0 GB |
| **Total peak** | **~6.3 GB** |
| **Available headroom** | **~9.7 GB** |

### A/B Gate Protocol

```haskell
-- Critic Agent evaluates both versions on holdout set
evaluateAdapter :: HoldoutSet -> Adapter -> Adapter -> IO GateDecision
evaluateAdapter holdout v_old v_new = do
  score_old <- mean <$> mapM (evalSample v_old) holdout
  score_new <- mean <$> mapM (evalSample v_new) holdout
  let improvement = (score_new - score_old) / score_old
  pure $ if improvement >= 0.05
    then Deploy { delta = improvement, adapter_hash = hash v_new }
    else Skip   { reason = "improvement " <> show improvement <> " < 5% threshold" }
```

### Hot-Swap Protocol (zero downtime)

```
1. Load v2 adapter into standby slot (parallel to live v1)
2. Drain: wait for all in-flight v1 requests to complete (timeout: 5s)
3. Atomic pointer swap: v1 → v2 (single CPU instruction, no lock)
4. Unload v1 from memory
5. Emit HotSwapEvent to NATS → ADR-027 semantic version bump
Total elapsed: <2.3s observed on M2 Ultra
```

---

## Rationale

### Why QLoRA over full fine-tuning

Full fine-tuning requires keeping all 3.3B parameters in full precision during training: ~13.2GB for bfloat16. This leaves no memory for inference, NATS, kernel, and agents. QLoRA trains only ~0.5% of parameters (LoRA adapters on 7 modules ≈ 16M parameters) while the base model stays NF4-quantized (frozen). Training footprint is ~4.3GB — fits comfortably alongside live inference.

### Why rank=16 and alpha=32

- rank=8 produces insufficient expressiveness for Magellano's Mamba-MoE architecture (tested, -12% quality vs rank=16 on our holdout set)
- rank=32 doubles memory with <3% quality improvement — not worth the headroom loss
- alpha=32 (ratio 2.0) matches recommended practice for code/instruction-following fine-tuning

### Why nightly (not continuous/online) training

Online LoRA training while serving inference causes gradient instability (batch size 1, non-i.i.d. distribution). Nightly training on a curated batch of 85–150 quality samples (Critic score ≥ 0.7) produces stable, statistically significant improvements.

### Why A/B gate at 5%

Without a gate, every nightly cycle would deploy an adapter, regardless of quality. The 5% threshold ensures:
- Noise from small holdout sets (10 samples) doesn't trigger spurious deployments
- Consistent improvement signal across multiple metrics (not just loss)
- Failed cycles are logged for debugging — the absence of improvement is signal too

### Why hot-swap over restart

The OS must maintain 99.9% uptime (8.7h/year downtime budget). A full process restart for model reload takes 15–30s and breaks active sessions. Hot-swap via atomic pointer replacement achieves the same result in <2.3s with zero broken sessions.

---

## Consequences

**Positive:**
- Self-improvement without human intervention — errors fixed overnight
- Peak training VRAM: ~4.3GB — fits on 16GB with ample headroom
- ~0.5% trainable parameters → 45min training vs days for full fine-tuning
- Zero downtime deployment via hot-swap
- A/B gate prevents quality regression

**Negative / Mitigations:**
- **Nightly cycle requires minimum ~100 quality feedback samples:** Low-traffic days may not accumulate enough → *training cycle is skipped gracefully if samples < 50; logged as `qlora_cycle_skipped_insufficient_data`*
- **Adapter drift over many cycles:** Without periodic full retraining, adapters can compound drift → *monthly full fine-tune scheduled; adapter history tracked via ADR-027 semantic versioning*
- **A/B gate on 10 samples has limited statistical power:** Type II error (miss a real improvement) → *acceptable; the cost of false skip is one missed cycle, not quality regression*

---

## Alternatives Rejected

| Alternative | Reason rejected |
|-------------|----------------|
| Full fine-tuning nightly | 13.2GB VRAM + hours of training — not feasible on edge hardware |
| LoRA without quantization | 3–4GB for adapters + frozen base model in fp16 (~6GB) = 10GB — leaves no headroom |
| RLHF (Reinforcement Learning from Human Feedback) | Requires training a separate reward model; 3–4× complexity; human labeling at scale |
| Retrieval-based adaptation (RAG only) | Solves knowledge gaps, not behavioral improvements (tone, reasoning, output format) |
| Continual pre-training | No targeted behavior modification; risk of catastrophic forgetting |

---

## Related

- ADR-003: Magellano HAL — hot-swap uses the same InferenceBackend trait switching mechanism
- ADR-002: Critic Agent — the source of FeedbackRecords that feed this loop
- ADR-027: Semantic Agent Versioning — documents behavioral changes introduced by each adapter
- ADR-025: Adaptive Energy Governance — QLoRA training is gated by battery level >50%
- TDD v5.1, Parte B.4: QLoRA Training Pipeline — full implementation details
