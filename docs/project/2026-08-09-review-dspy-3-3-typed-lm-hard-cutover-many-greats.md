---
summary: "Many-of-the-greats review synthesis for the DSPy 3.3 typed-LM hard-cutover RFC."
read_when:
  - "Reviewing Decision 118 or the typed-LM cutover rationale."
type: "review"
---

# Review synthesis: DSPy 3.3 typed-LM hard cutover

## Reviewed artifact

`docs/project/2026-08-09-dspy-3-3-typed-lm-hard-cutover-rfc.md`

Review procedure: Prompt Vault `many-of-the-greats`, registry `a5920542375bf4e3c6f09b22c081b8cff29cad5f73da592ad43c9cde8ad57917`, dispatch posture `text_ok`.

Independent inputs:

- clean-break/API replacement: `dispatch-1786314254545`
- ports-and-adapters / anti-corruption boundary: `dispatch-1786314254546`
- runtime safety and effect custody: `dispatch-1786314254547`
- pragmatic vertical slice: `dispatch-1786314254548`
- exact DSPy 3.3 API and DSPx impact map: `dispatch-1786314254549`

Synthesis owner: AK-4728 agent. Synthesis rule: explicit adjudication; unanimity is not required, but every blocker must be resolved or carried as a binding implementation constraint.

## Question

What architecture truthfully removes DSPx's DSPy legacy bridge while enabling an exact DSPy 3.3 typed-LM cutover without surrendering DSPx provider, effect, receipt, and domain authority?

## Mode 1 — many of the greats

### School 1: Upstream-native clean break

- Core claim: adopt DSPy 3.3 typed `BaseLM` directly and delete every legacy request/response facsimile.
- Premises: the normalized upstream API is now the real extension contract; transitional compatibility code compounds debt.
- Strongest case: nine typed implementations are clearer than nine legacy ones, and upstream types already encode tools, reasoning, media, usage, and failure structure.
- What it sees: superficial compatibility is more dangerous than explicit breakage.

### School 2: Ports and adapters

- Core claim: transport providers must not inherit upstream orchestration lifecycle at all; one anti-corruption adapter should own DSPy coupling.
- Premises: DSPx owns empirical provider/effect semantics, while DSPy owns module-facing normalized request/response semantics.
- Strongest case: direct conversion of all providers leaves mixed history, state, callback, copy, and effect ownership in every object. One adapter localizes translation and upgrade risk.
- What it sees: replacing a method signature is not architectural decoupling.

### School 3: Runtime safety and effects

- Core claim: no typed migration is valid unless every invocation has a truthful effect disposition and indeterminate effects are terminal.
- Premises: CLI, RPC, HTTP, fallback, and cancellation can cross external-effect boundaries before failure becomes observable.
- Strongest case: current permissive errors and fallback can turn failures into completions or duplicate effects. Typed DTOs do not solve custody by themselves.
- What it sees: async, callbacks, and cancellation labels can produce false confidence while work continues.

### School 4: Product vertical slice

- Core claim: cut the support matrix to the smallest real path, ship the architectural spine, and re-add providers only when proven.
- Premises: all-provider parity and excluded GEPA production paths are not prerequisites for a trusted-local typed Core.
- Strongest case: stub-first plus one real provider proves the architecture; dormant best-effort providers produce fictitious breadth.
- What it sees: compatibility matrices can preserve features the product does not need.

## Mode 2 — confrontation

### Clash 1: direct upstream adoption vs anti-corruption boundary

- Fundamental contradiction: whether provider implementations should themselves be DSPy objects.
- Direct adoption explains the typed surface with least translation.
- Ports and adapters better preserves DSPx's effect/receipt authority and avoids nine copies of upstream lifecycle coupling.
- Decision: ports and adapters dominates because transport effects and DSPy orchestration have different owners. The clean-break demand survives as deletion of all legacy provider inheritance and response facsimiles.

### Clash 2: broad migration vs vertical cut

- Fundamental contradiction: whether all current provider names remain available during cutover.
- Broad migration preserves feature inventory but multiplies simultaneous ambiguity.
- Vertical slicing makes unsupported providers unavailable and restores them through evidence.
- Decision: vertical slicing dominates rollout. Hard breaking means truthful removal, not compatibility theater.

### Clash 3: feature momentum vs effect custody

- Fundamental contradiction: whether fallback, parallelism, async, and streaming can be inferred from transport implementation details.
- Product momentum favors wrappers and continued availability.
- Safety shows that thread wrapping, daemon races, broad exception fallback, and completion-text errors can hide or duplicate effects.
- Decision: runtime safety is non-negotiable. Unsupported operations reject before effects; indeterminate operations terminate the aggregate.

### Clash 4: GEPA compatibility gate vs trusted-local production scope

- Fundamental contradiction: whether a pickle-backed path excluded from production should block the typed dependency transaction.
- Compatibility discipline values the real end-to-end proof.
- Product scope excludes the artifact class regardless of proof.
- Decision: retain AK-4725 as truthful evidence and keep the real-output journey as optional compatibility work, but remove it as a production cutover prerequisite.

## Mode 3 — integration or decision

- Chosen path: **explicit preference**.
- Result: adopt a hard ports-and-adapters cutover with one DSPy 3.3 typed adapter, DSPx-owned providers and effect DTOs, stub-first migration, explicit provider unavailability, and exact dependency pinning.
- Why: this is the only option that removes both the old method bridge and the deeper dual-owner provider object while preserving the strongest safety constraints.
- Remaining unresolved: provider-by-provider restoration order after the first real supported route; exact non-text typed parts to add after text-only acceptance; separately gated native async/cancellation.

## Blocking implementation constraints

1. No transport provider may remain a DSPy subclass after its migration slice.
2. No fake OpenAI response envelope or legacy response parser may remain on the canonical path.
3. Unsupported typed parts and settings must fail before provider effects.
4. One DSPx invocation yields one effect disposition; indeterminate forbids retry/fallback.
5. `MultiProviderLM` is removed, not patched in place.
6. Registry support is explicit; import failures are not swallowed as discovery.
7. The first canonical transaction supports only migrated providers.
8. Exact installed-wheel and rollback proof are mandatory.
9. GEPA pickle compatibility remains excluded from the trusted-local production matrix.

## Review outcome

**`ready_for_adr`**

Legal next move: record an ADR adopting the RFC, then execute the linked implementation/validation/rollback plan through scoped AK tasks. No provider or dependency mutation is authorized by this review artifact alone.
