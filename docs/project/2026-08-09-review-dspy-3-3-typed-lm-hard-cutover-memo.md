---
summary: "Controlling review memo for the DSPy 3.3 typed-LM hard-cutover RFC."
read_when:
  - "Checking Decision 118 review closure or ADR legality."
type: "review"
---

# Review memo: DSPy 3.3 typed-LM hard cutover

## Reviewed artifact

`docs/project/2026-08-09-dspy-3-3-typed-lm-hard-cutover-rfc.md`

## Inputs

- controlling many-of-the-greats synthesis: `2026-08-09-review-dspy-3-3-typed-lm-hard-cutover-many-greats.md`
- exact review dispatches: `dispatch-1786314254545`, `dispatch-1786314254546`, `dispatch-1786314254547`, `dispatch-1786314254548`, and `dispatch-1786314254549`
- historical falsifiers: AK-4722 and AK-4725

## Findings

The RFC removes rather than renames the legacy bridge. The decisive boundary is one typed DSPy adapter over DSPx-owned provider ports. It rejects direct all-provider DSPy inheritance because that would retain mixed lifecycle and effect ownership. It also rejects permanent stub-only scope: stub is the offline canary, while providers return additively through the new contract.

The review's safety blockers are binding implementation constraints: unsupported typed content rejects before effects; indeterminate effects terminate retry/fallback; provider failures cannot become answer text; async, cancellation, and streaming cannot be fabricated; registry availability is explicit; `MultiProviderLM` is removed rather than patched.

S4b remains truthful compatibility evidence. Removing pickle-backed GEPA materialization as a production cutover prerequisite is coherent because the target matrix already excludes that artifact class. A later real-output journey may prove compatibility without changing the production exclusion.

## Outcome

**`ready_for_adr`**

## Legal next move

Record the ADR and implementation/validation/rollback plan, advance Decision 118 through AK's ADR workflow, re-evaluate linked execution tasks, and implement only through scoped post-ADR tasks. This memo authorizes no dependency, provider, release, publication, activation, credential, network, or external-tool effect by itself.
