---
summary: "ADR index and conventions for architecture decision records."
read_when:
  - "You are making a durable architecture or runtime decision."
  - "You need prior decision context before changing providers, policy, or contracts."
---

Architecture Decision Records (ADRs)
====================================

Purpose
-------
ADRs capture durable architecture decisions with enough context to explain *why* a path was chosen and what tradeoffs were accepted.

Naming convention
-----------------
- File name: `YYYYMMDD-short-title.md`
- Example: `20260206-pi-rpc-provider.md`

Required template fields
------------------------
Each ADR should include these sections:
- `Context`
- `Decision`
- `Consequences`
- `Status` (e.g., Proposed, Accepted, Superseded)

Index
-----

| ADR | Title | Status | Notes |
| --- | --- | --- | --- |
| [20260206-pi-rpc-provider.md](20260206-pi-rpc-provider.md) | Pi provider runtime uses persistent RPC process | Accepted | Provider-first integration; avoids shelling out one-shot per LM call. |
| [20260322-provider-runtime-v4.md](20260322-provider-runtime-v4.md) | Provider runtime v4 is the local mixed-provider unblock path | Accepted | Keeps template-adapter optional while shipping explicit `vllm-local` + `dspy-lm-auth` provider workflows. |
| [20260322-synthesis-architecture-v7-v9.md](20260322-synthesis-architecture-v7-v9.md) | Synthesis architecture targets V7 operational delivery on a V9-compatible core | Accepted | Defines the repo's dated references for V7/V8/V9 and the implementation posture to architect for V9 while shipping V7 first. |
| [20260323-synthesis-evidence-retrieval-v1.md](20260323-synthesis-evidence-retrieval-v1.md) | Synthesis evidence retrieval contract v1 | Accepted | Freezes the first SG2 evidence bundle: exact-match module-gen receipts, replay health, then Oracle neighbors. |
| [20260324-synthesis-evidence-history-advisory-v1.md](20260324-synthesis-evidence-history-advisory-v1.md) | Synthesis evidence history advisory contract v1 | Accepted | Defines the first post-diagnostics SG2 evidence consumer: a read-only historical convergence advisory for selected module artifacts. |
| [20260327-synthesis-evidence-candidate-prior-v1.md](20260327-synthesis-evidence-candidate-prior-v1.md) | Synthesis evidence candidate-prior contract v1 | Accepted | Freezes the first candidate-level prior boundary: replay-healthy exact-match winner history can inform read-only per-candidate priors, but not ranking or pruning yet. |
| [20260327-synthesis-evidence-candidate-prior-audit-v1.md](20260327-synthesis-evidence-candidate-prior-audit-v1.md) | Synthesis evidence candidate-prior audit contract v1 | Accepted | Defines the first bounded consumer of `candidate_winner_priors`: a post-selection audit comparing the selected candidate to the current fan-out's positive prior support. |
| [20260328-synthesis-evidence-candidate-prior-divergence-explanation-v1.md](20260328-synthesis-evidence-candidate-prior-divergence-explanation-v1.md) | Synthesis evidence candidate-prior divergence explanation contract v1 | Accepted | Freezes the next post-audit explanation layer: when prior-supported candidates are not selected, DSPx explains whether they failed runtime checks or still lost under trusted current V7 ranking. |
| [20260328-synthesis-evidence-candidate-prior-readiness-advisory-v1.md](20260328-synthesis-evidence-candidate-prior-readiness-advisory-v1.md) | Synthesis evidence candidate-prior readiness advisory contract v1 | Accepted | Freezes the next post-divergence governance layer: DSPx summarizes whether receipt-backed candidate priors look convergent, runtime-failure-limited, scoring-limited, sparse, or mixed before any ranking contract widens authority. |
| [20260328-synthesis-evidence-candidate-prior-counterfactual-advisory-v1.md](20260328-synthesis-evidence-candidate-prior-counterfactual-advisory-v1.md) | Synthesis evidence candidate-prior counterfactual advisory contract v1 | Accepted | Freezes the next post-readiness SG2 layer: DSPx surfaces bounded current-run prior-supported alternatives for governance review before any predictive-ranking authority widens. |
| [20260329-synthesis-evidence-shadow-predictive-ranking-advisory-v1.md](20260329-synthesis-evidence-shadow-predictive-ranking-advisory-v1.md) | Synthesis evidence shadow predictive-ranking advisory contract v1 | Accepted | Freezes the next SG2 shadow layer: DSPx computes a bounded prior-aware shadow preference for governance inspection before any live evidence-aware ranking authority widens. |
| [20260330-synthesis-evidence-governed-policy-evaluation-contract-v1.md](20260330-synthesis-evidence-governed-policy-evaluation-contract-v1.md) | Synthesis evidence governed policy-evaluation contract v1 | Accepted | Freezes the first governance-only contract for evaluating named ranking or promotion-policy variants against shadow predictive-ranking evidence without mutating live V7 behavior. |
| [20260409-human-governed-promotion-eligibility-contract-v1.md](20260409-human-governed-promotion-eligibility-contract-v1.md) | Human-governed promotion-eligibility contract v1 | Accepted | Freezes how governance-only policy-evaluation receipts plus runtime-spine provenance may nominate named policy variants for explicit human review toward future live authority without changing live V7 behavior. |
| [20260410-human-governed-review-decision-contract-v1.md](20260410-human-governed-review-decision-contract-v1.md) | Human-governed review-decision contract v1 | Accepted | Freezes how explicit humans resolve nominated governance-only policy variants toward later off-run policy/version change without changing the generating run's live behavior. |
