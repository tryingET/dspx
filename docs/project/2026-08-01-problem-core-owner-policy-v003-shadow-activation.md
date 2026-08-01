---
summary: "Tier 1 problem brief for enabling the first immutable owner-policy successor solely to run a real authority-false FIDO shadow dogfood."
read_when:
  - "Reviewing why Decision 96 acceptance does not itself enable owner policy or authorize a real signature."
  - "Checking the activation-decision artifact chain for owner policy v003."
type: "problem_brief"
---

# Problem Brief — Core owner-policy v003 shadow activation

## Trigger

Decision 96 accepted the concentrated single-owner FIDO architecture and is unblocked, but its accepted selector resolves immutable owner policy v002, which remains disabled. The consumer is implemented and hard-wired authority-false, yet the integrated path has not run with a current enabled owner-policy generation, fresh exact payload, real YubiKey Bio UP+UV signature, durable consume, and replay/drift proof.

## Problem

Architecture acceptance cannot substitute for activation of exact policy bytes. Rewriting v002 would destroy history and anti-rollback integrity. Treating the old expired signature fixture as live approval would reuse stale bytes and bypass current evidence, policy, and nonce state. Enabling authority true at the same time would collapse shadow proof into release authorization.

The project needs one separately reviewed activation decision that binds an immutable v003 policy and selector, makes that selector current through AK, and permits only a non-publishing `shadow_verified_not_authorized` dogfood.

## Evidence

- Decision 96 recorded and unblocked the architecture with v002 selector evidence.
- Live preflight resolves v002 as the current owner generation and records a monotonic owner-policy checkpoint at version 2.
- Commit `2839e8fc` provides coherent one-read artifact staging and retained nonce-ledger identity.
- The existing expired real SSHSIG proves only parser/OpenSSH UP+UV handling, not current approval.
- `docs/project/2026-08-01-core-single-owner-fido-shadow-repair.md` records the authority-false foundation and validation evidence.
- `docs/project/2026-08-01-plan-core-single-owner-fido-activation.md` requires a distinct activation decision before any enabled successor or ceremony.

## Why Tier 1

The change selects current enabled authority-policy bytes and advances an anti-rollback checkpoint. Even though the consumer remains false, that changes the live policy lineage that later authorization depends on. Exact policy/selector bytes, review closure, rollback, and currentness must therefore pass the architecture decision membrane.

## Decision requested

Accept one immutable v003 generation that:

- preserves the same named owner and pinned FIDO public key/fingerprint;
- preserves SSHSIG namespace, UP+UV, 15-minute lifetime, fresh nonce, and concentrated-risk invariants;
- sets `authorization_enabled=true` and `disabled_reason=null`;
- keeps `package_publication=false` and `sdist_supported=false`;
- supersedes v002 through a new exact Git-bound selector and AK decision;
- authorizes only one fresh authority-false shadow dogfood plus negative tests.

## Non-goals

This decision does not authorize an authority-true consumer, package publication, registry credentials, sdist support, policy-history rewrite, checkpoint rollback, nonce reuse, private-key/PIN capture, or GitHub mutation beyond read-only observations.
