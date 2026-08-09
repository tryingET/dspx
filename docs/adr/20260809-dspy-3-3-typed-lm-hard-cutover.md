---
summary: "Adopts a hard cutover to one DSPy 3.3 typed-LM adapter over DSPx-owned provider ports."
read_when:
  - "Changing DSPx providers, LM DTOs, DSPy integration, or dependency bounds."
type: "decision"
---

# ADR: DSPy 3.3 typed-LM hard cutover

## Status

Accepted by Decision 118.

Accepted RFC: `../project/2026-08-09-dspy-3-3-typed-lm-hard-cutover-rfc.md`

Controlling review: `../project/2026-08-09-review-dspy-3-3-typed-lm-hard-cutover-many-greats.md` with outcome `ready_for_adr`.

Implementation plan: `../project/2026-08-09-dspy-3-3-typed-lm-hard-cutover-implementation-plan.md`.

## Context

DSPx's nine provider classes combine transport logic, DSPx DTO behavior, and DSPy `BaseLM` lifecycle behavior. DSPy 3.3 introduces an explicit typed custom-LM contract. Repairing the legacy bridge would preserve the wrong seam; converting every provider directly into a typed DSPy subclass would preserve the deeper ownership conflation.

The trusted-local Core target needs exact, truthful provider support and effect evidence, not compatibility breadth. Pickle-backed GEPA artifacts are already excluded from that production matrix.

## Decision

DSPx will make a hard breaking cutover to DSPy 3.3 with these rules:

1. Transport providers implement DSPx-owned provider ports and do not inherit DSPy classes.
2. Exactly one `DSPyTypedLMAdapter` subclasses `dspy.BaseLM`, declares `forward_contract = "typed_lm"`, and translates between DSPy and DSPx types.
3. DSPx request/result/effect types remain nominally distinct and authoritative for provider invocation and receipts.
4. Unsupported DSPy typed parts, tools, settings, async, cancellation, or streaming fail explicitly before effects.
5. Indeterminate effects are terminal and cannot be retried, hidden as completion text, or followed by aggregate fallback.
6. Providers are restored one at a time through an explicit support allowlist. Stub is the first canary.
7. Every importable legacy provider subclass, legacy OpenAI-shaped response facsimile/parser, registration/export path, and `MultiProviderLM` is deleted before the canonical dependency move.
8. The canonical dependency/source/lock move is one exact reviewed transaction with installed-wheel and rollback proof.
9. AK-4722 and AK-4725 remain immutable historical evidence. S3 legacy-bridge repair and S4b pickle materialization are no longer prerequisites for the typed trusted-local Core.
10. GEPA real-output materialization remains optional compatibility work and cannot enter the trusted-local production matrix while it depends on pickle-backed whole programs.

## Consequences

- Existing provider class consumers and DSPx LM DTO consumers must migrate.
- Provider availability temporarily contracts to the explicitly migrated set.
- Upstream DSPy coupling is localized to one adapter.
- DSPx retains provider effect, receipt, redaction, and empirical evidence authority.
- No source-level bridge or runtime compatibility guarantee with DSPy 3.1.3 remains after the canonical cutover; 3.1.3 is rollback evidence only.
- ReActV2, Flex, external tools, hosted runtime, release, publication, and activation remain separate gates.

## Validation obligations

- exact DSPy/DSPy-AI 3.3.0 and complete lock identity;
- typed request/response tests against the exact upstream API;
- pre-effect rejection tests for unsupported typed content;
- effect-disposition and non-retry tests;
- provider registry support-matrix tests;
- generated-program guard and receipt regressions;
- clean installed-wheel proof with no source-checkout leakage;
- independent architecture and runtime-safety review.

## Rollback

For a full rollback after any typed wave, revert every cutover and later provider/aggregate commit to the immutable pre-cutover 3.1.3 source generation, restore its exact wheel/lock/environment, and quarantine version-bound 3.3 provider state, receipts, caches, and artifacts. A bounded post-cutover provider rollback may revert only that additive provider while retaining the accepted typed runtime. Never mix typed source with 3.1.3 dependencies or restore legacy provider inheritance into the typed environment.
