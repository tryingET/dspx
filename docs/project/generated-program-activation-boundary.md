---
summary: "DSPx generated-program activation packet boundary: evidence only until owner, decision, canonical binding, rollout owner, and rollback are explicit."
read_when:
  - "You are using `dspx program-promote activation-packet`."
  - "You need to know why a generated program remains blocked after Oracle/jury evidence exists."
  - "You are checking the authority/activation gates for generated DSPy/cognition programs."
---

# Generated program activation boundary

DSPx can produce activation evidence packets for generated DSPy/cognition programs, but those packets are not production activation authority.

Canonical society-wide semantics live in governance-kernel:

- `~/ai-society/holdingco/governance-kernel/docs/core/definitions/generated-dspy-program-promotion-governance.md`
- `~/ai-society/holdingco/governance-kernel/docs/core/definitions/transition-passports/generated-cognition-program-production-activation.md`

## Hard boundary

`dspx program-promote activation-packet` may write a non-authoritative evidence packet. It must not:

- promote a generated program;
- deploy or route a generated program;
- mutate AK / society authority;
- mutate governance-kernel;
- mutate MLflow;
- mutate Oracle indexes;
- treat Oracle, MLflow, or DSPx jury output as approval.

## Rollout gate

A packet may reach `ready_for_rollout_preflight` only when all activation authority fields are explicit:

1. owning domain;
2. authority owner / delegated adjudicator;
3. required behavior evidence;
4. Oracle report when required;
5. jury/review evidence when required;
6. decision record with `outcome=promote`;
7. canonical binding ref;
8. rollout owner;
9. rollback plan.

If `rollout_owner` is missing, the packet stays `blocked` even if decision and canonical binding refs are present.

## Practical consequence

Oracle production-adjacent readiness on DS1621 improves the evidence substrate. It does not change the activation judge. A generated program still needs a domain-governed decision, canonical binding, rollout owner, and rollback plan before any production activation can be claimed.
