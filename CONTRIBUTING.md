# Contributing to AI OS — Magellano Architecture

Thank you for your interest. This is a **pre-PoC architecture project** — we are at the whitepaper → prototype transition. Contributions at this stage are primarily about design validation, not code.

---

## Current Phase: Architecture → PoC

The full Technical Design Document (TDD v5.1, 4630+ .md lines) is in `docs/`. Before writing any code, read the relevant section for the component you want to contribute to.

**Active PoC targets (Phase α):**
- Rust kernel skeleton (Tokio + tonic/gRPC)
- Planner Agent — DAG construction (rule engine, no LLM required)
- Bus 1 (Controllo) — gRPC Protobuf service definitions
- Agent Registry — Gossip-based service discovery

---

## Skills We Need

| Area | Stack | TDD Section |
|------|-------|-------------|
| Kernel core | Rust, Tokio, async | Parte A, B, C |
| gRPC / message bus | tonic, Protobuf, NATS | Parte D (Bus 1, Bus 2) |
| Inference engine | Swift, Metal, CoreML | Parte B (Magellano HAL) |
| Agent protocol | FIPA-ACL, Rust | Parte A (Tassonomia) |
| Vector search | FAISS, Rust/Python | Parte E (Memory Layer) |
| Consensus | openraft, Raft | ADR-004 |
| Observability | Prometheus, OTel | Parte G |
| Security | Zero Trust, ED25519 | Parte H |

---

## How to Contribute

### 1. Read First

- `docs/AI_OS_TDD_v5_1.md` — full specification
- `docs/ADR/` — architecture decisions (understand *why* before proposing alternatives)

### 2. Open a Discussion Issue

Before writing any code, open a GitHub Discussion:
- Tag it with the component name (e.g., `[Kernel]`, `[Magellano]`, `[Bus-1]`)
- Reference the TDD section you are implementing
- Describe your approach and any deviations from the spec

### 3. Implementation Guidelines

- **Rust code:** follow `clippy --all-targets -D warnings`. No `unwrap()` in production paths.
- **Swift code:** follow SwiftLint rules (`.swiftlint.yml` will be added at PoC start)
- **Tests:** all PRs must include unit tests. Integration tests where applicable.
- **Commit messages:** Conventional Commits format (`feat:`, `fix:`, `docs:`, `test:`)

### 4. Pull Request Process

1. Fork → branch (`feature/component-name`)
2. Open Draft PR early — discuss before completing
3. Reference the TDD section in the PR description
4. All CI checks must pass (cargo test, cargo clippy, cargo audit)
5. At least one review required before merge

---

## Architecture Governance

The TDD v5.1 is the source of truth. Proposals to deviate from it require an ADR (Architecture Decision Record) — see `docs/ADR/` for the format. Submit ADR proposals as GitHub Discussions with the `[ADR]` tag.

**Do not propose:**
- Replacing Rust with Python for the kernel (see ADR-001 rationale)
- Replacing FIPA-ACL with ad-hoc JSON messages
- Pooled agents instead of agent-per-resource at Tier 3 (see ADR-002)

These have been evaluated and rejected. The ADRs explain why.

---

## Code of Conduct

Technical disagreements are expected and welcome. Personal attacks are not. Be direct, cite the spec, propose alternatives with data.

---

## License

By contributing, you agree that your contributions will be licensed under Apache 2.0 (code) and CC BY-SA 4.0 (documentation).
